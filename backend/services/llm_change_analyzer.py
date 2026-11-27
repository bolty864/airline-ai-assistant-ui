"""GPT-4o analysis of ONE regulatory change: summary, impacted controls / systems / teams, remediation actions.

The model only chooses among candidates the rules already found (Agent 3's mappings and the registers), so it cannot
invent a control or a system. Everything it returns is validated here.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import APIError, BadRequestError

from services.impact_types import ChangeAnalysis, ChangeType, DiffEntry, ImpactContext
from services.regulator_profiles import RegulatorProfile
from services.remediation_service import describe_change
from settings import Settings

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "change_impact_prompt.txt"
PROMPT_VERSION = "impact-v1"
MAX_ACTIONS, MAX_TEAMS = 4, 4

CHANGE_SCHEMA = {
    "name": "change_impact",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "material", "change_type", "impacted_control_codes", "impacted_system_codes",
                     "impacted_teams", "remediation", "confidence"],
        "properties": {
            "summary": {"type": "string"},
            "material": {"type": "boolean"},
            "change_type": {"type": "string", "enum": ChangeType.ALL},
            "impacted_control_codes": {"type": "array", "items": {"type": "string"}},
            "impacted_system_codes": {"type": "array", "items": {"type": "string"}},
            "impacted_teams": {"type": "array", "items": {"type": "string"}},
            "remediation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["task_name", "owner_team", "detail"],
                    "properties": {"task_name": {"type": "string"}, "owner_team": {"type": "string"},
                                  "detail": {"type": "string"}},
                },
            },
            "confidence": {"type": "number"},
        },
    },
}


class ChangeLLMError(Exception):
    pass


def render_user_message(entry: DiffEntry, ctx: ImpactContext, regulator: str, document_title: str,
                        profile: RegulatorProfile | None) -> str:
    lines = [
        "REGULATOR",
        f"{profile.code} - {profile.name}. Typically governs: {profile.focus}" if profile else f"{regulator} (not a profiled regulator)",
        f"Document: {document_title}", "",
        "CHANGE",
        f"Proposed type: {entry.change_type}", f"Subject area (rules): {entry.domain.lower()}",
        f"Clause: {entry.clause_ref or 'n/a'}",
        f"OLD: {entry.old.text if entry.old else '(did not exist)'}",
        f"NEW: {entry.new.text if entry.new else '(removed)'}",
    ]
    if entry.quantity_changes:
        lines.append(f"Numbers changed (rules): {describe_change(entry)}")
    if entry.modal_change:
        lines.append(f"Mandatory wording changed (rules): {entry.modal_change[0]} -> {entry.modal_change[1]}")
    if entry.severity_old != entry.severity_new and entry.severity_old and entry.severity_new:
        lines.append(f"Severity changed (rules): {entry.severity_old} -> {entry.severity_new}")
    lines.append(f"Obligation owner: {ctx.obligation_owner or 'n/a'}")
    lines.append("")

    lines.append("CONTROLS" if ctx.controls else "CONTROLS: none")
    for c in ctx.controls:
        lines += [f"[{c.code}] {c.name}", f"Description: {c.description or 'n/a'}",
                  f"Owner: {c.owner_function or 'n/a'}; frequency: {c.frequency or 'n/a'}; automation: {c.automation_level or 'n/a'}"]
    lines.append("")
    lines.append("SYSTEMS" if ctx.systems else "SYSTEMS: none")
    for s in ctx.systems:
        lines += [f"[{s.code}] {s.name}", f"Description: {s.description or 'n/a'}",
                  f"Criticality: {s.criticality or 'n/a'}; owner: {s.owner_function or 'n/a'}"]
    lines.append("")
    lines.append("POLICIES" if ctx.policies else "POLICIES: none")
    lines += [f"- {p['name']}" for p in ctx.policies]
    if ctx.gap:
        lines += ["", "EXISTING GAP",
                  f"{ctx.gap.get('gap_type')} (risk {ctx.gap.get('risk_rating')}, coverage {ctx.gap.get('coverage_score')}%)"]
    return "\n".join(lines).strip()


class ChangeAnalyzer:
    def __init__(self, client, settings: Settings, prompt_path: Path = PROMPT_PATH):
        self.client = client
        self.settings = settings
        self.deployment = settings.azure_openai_deployment
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    async def analyze(self, entry: DiffEntry, ctx: ImpactContext, regulator: str, document_title: str,
                      profile: RegulatorProfile | None) -> ChangeAnalysis:
        messages = [{"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": render_user_message(entry, ctx, regulator, document_title, profile)}]
        prompt_tokens = completion_tokens = 0
        last_error = "unknown"
        for attempt in (1, 2):                            # one retry for malformed / truncated JSON
            try:
                resp = await self.client.chat.completions.create(
                    model=self.deployment, messages=messages, temperature=0,
                    max_tokens=self.settings.impact_max_completion_tokens,
                    response_format={"type": "json_schema", "json_schema": CHANGE_SCHEMA},
                )
            except BadRequestError as exc:
                raise ChangeLLMError(f"bad_request: {exc.message}"[:500]) from exc
            except APIError as exc:
                raise ChangeLLMError(f"api_error: {exc}"[:500]) from exc
            if resp.usage:
                prompt_tokens += resp.usage.prompt_tokens
                completion_tokens += resp.usage.completion_tokens
            try:
                result = self.validate(json.loads(resp.choices[0].message.content or ""), entry, ctx)
                result.prompt_tokens, result.completion_tokens = prompt_tokens, completion_tokens
                return result
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                last_error = f"invalid_json: {exc}"[:300]
                log.warning("Invalid change-analysis JSON", extra={"impact_key": entry.key, "attempt": attempt})
        raise ChangeLLMError(last_error)

    @staticmethod
    def validate(raw: dict, entry: DiffEntry, ctx: ImpactContext) -> ChangeAnalysis:
        warnings: list[str] = []
        control_codes = {c.code for c in ctx.controls}
        system_codes = {s.code for s in ctx.systems}
        controls = [c for c in dict.fromkeys(raw["impacted_control_codes"]) if c in control_codes]
        systems = [s for s in dict.fromkeys(raw["impacted_system_codes"]) if s in system_codes]
        if len(controls) != len(set(raw["impacted_control_codes"])) or len(systems) != len(set(raw["impacted_system_codes"])):
            warnings.append("Model named a control or system that is not a candidate; ignored.")

        change_type = entry.change_type
        specific = {ChangeType.RETENTION, ChangeType.REPORTING, ChangeType.SECURITY}
        if entry.change_type == ChangeType.MODIFIED and raw["change_type"] in specific and not entry.minor:
            change_type = raw["change_type"]              # only the generic type may be refined

        teams = []
        for t in raw["impacted_teams"]:
            t = " ".join(str(t).split())[:100]
            if t and t.lower() not in {x.lower() for x in teams}:
                teams.append(t)

        actions = []
        for a in raw["remediation"][:MAX_ACTIONS]:
            name = " ".join(str(a.get("task_name", "")).split())
            if name:
                actions.append({"task_name": name[:200], "owner_team": " ".join(str(a.get("owner_team", "")).split())[:100],
                                "detail": " ".join(str(a.get("detail", "")).split())[:500]})
        if not (raw["summary"] or "").strip():
            raise ValueError("empty summary")
        return ChangeAnalysis(
            summary=" ".join(raw["summary"].split()), material=bool(raw["material"]), change_type=change_type,
            control_codes=controls, system_codes=systems, teams=teams[:MAX_TEAMS], actions=actions,
            confidence=max(0.0, min(1.0, float(raw["confidence"]))), warnings=warnings,
        )
