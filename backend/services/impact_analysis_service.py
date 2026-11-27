"""Turns a detected change into a complete impact: affected controls, systems and teams, GPT-4o analysis, risk, tasks.

Control / system candidates come from Agent 3's mappings (and the mappings the obligation had in the previous version),
plus the systems linked to those controls. GPT-4o confirms which of them really have to change.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from collections.abc import Sequence

from services import remediation_service, risk_service
from services.gap_types import AssetView
from services.impact_types import (ChangeAnalysis, ChangeType, DiffEntry, ImpactContext, ImpactDraft, ObligationRec)
from services.llm_change_analyzer import PROMPT_VERSION, ChangeAnalyzer, ChangeLLMError
from services.regulator_profiles import resolve_regulator
from settings import Settings

log = logging.getLogger(__name__)

MAX_CONTROLS, MAX_SYSTEMS, MAX_POLICIES = 5, 5, 3
DETERMINISTIC_CONFIDENCE = 0.90      # rule-only findings (removed, severity, wording-only)
LLM_FAILED_CONFIDENCE = 0.50         # the change was detected but GPT-4o could not analyse it
_CRITICALITY_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
_NEEDS_LLM = {ChangeType.NEW, ChangeType.MODIFIED, ChangeType.RETENTION, ChangeType.REPORTING, ChangeType.SECURITY}


# ------------------------------------------------------------------ record builders
def asset_to_dict(a: AssetView) -> dict:
    name = f"{a.name} section {a.section_ref}" if a.target_type == "POLICY_SECTION" and a.section_ref else a.name
    return {"type": a.target_type, "code": a.code, "name": name, "owner": a.owner_function, "link_type": a.link_type,
            "relevance": a.relevance}


def records_from_obligations(obligations: Sequence, assets: dict[int, list[AssetView]]) -> list[ObligationRec]:
    return [ObligationRec(
        text=o.obligation_text, clause_ref=o.clause_ref, severity=o.severity, obligation_type=o.obligation_type,
        owner_function=o.owner_function, target_system=o.target_system, citation=o.citation,
        confidence=float(o.confidence_score) if o.confidence_score is not None else None, embedding=o.embedding,
        obligation_id=o.id, mapping_status=o.mapping_status, mapped_at=o.mapped_at,
        assets=[asset_to_dict(a) for a in assets.get(o.id, [])]) for o in obligations]


def records_from_versions(rows: Sequence) -> list[ObligationRec]:
    return [ObligationRec(
        text=r.obligation_text, clause_ref=r.clause_ref, severity=r.severity, obligation_type=r.obligation_type,
        owner_function=r.owner_function, target_system=r.target_system, citation=r.citation,
        confidence=float(r.confidence_score) if r.confidence_score is not None else None, embedding=r.embedding,
        snapshot_id=r.id, assets=list(r.mapped_assets or [])) for r in rows]


class ImpactAnalysisService:
    def __init__(self, analyzer: ChangeAnalyzer, settings: Settings):
        self.analyzer = analyzer
        self.settings = settings

    # ------------------------------------------------------------------ candidates
    @staticmethod
    def _ordered_assets(entry: DiffEntry) -> list[dict]:
        """Assets of the new obligation first (best relevance first), then those of the old one."""
        out: list[dict] = []
        for rec in (entry.new, entry.old):
            if rec:
                out += sorted(rec.assets, key=lambda a: (a.get("link_type") != "DIRECT", -float(a.get("relevance") or 0)))
        return out

    def candidate_codes(self, entry: DiffEntry) -> tuple[list[str], list[str]]:
        assets = self._ordered_assets(entry)
        controls = list(dict.fromkeys(a["code"] for a in assets if a["type"] == "CONTROL"))[:MAX_CONTROLS]
        systems = list(dict.fromkeys(a["code"] for a in assets if a["type"] == "SYSTEM"))
        return controls, systems

    def build_context(self, entry: DiffEntry, controls_by_code: dict[str, AssetView],
                      systems_by_code: dict[str, AssetView], linked: dict[str, list[str]], gap: dict | None) -> ImpactContext:
        assets = self._ordered_assets(entry)
        control_codes, system_codes = self.candidate_codes(entry)
        controls = [controls_by_code[c] for c in control_codes if c in controls_by_code]
        for c in controls:                                             # systems the controls run on
            system_codes += linked.get(c.code, [])
        systems = [systems_by_code[s] for s in dict.fromkeys(system_codes) if s in systems_by_code][:MAX_SYSTEMS]
        policies = [{"code": a["code"], "name": a["name"]} for a in assets if a["type"] == "POLICY_SECTION"]
        direct = {a["code"] for a in assets if a.get("link_type") == "DIRECT" and a["type"] in ("CONTROL", "SYSTEM")}
        rec = entry.new or entry.old
        return ImpactContext(controls=controls, systems=systems, policies=policies[:MAX_POLICIES], direct_codes=direct,
                             obligation_owner=rec.owner_function if rec else None, gap=gap)

    # ------------------------------------------------------------------ fingerprint
    def fingerprint(self, entry: DiffEntry, ctx: ImpactContext, regulator: str) -> str:
        s = self.settings
        payload = {
            "k": entry.key, "t": entry.change_type, "sev": [entry.severity_old, entry.severity_new],
            "c": [[c.code, c.name, c.description, c.owner_function, c.frequency, c.automation_level, c.test_result]
                  for c in ctx.controls],
            "s": [[x.code, x.name, x.criticality, x.owner_function] for x in ctx.systems],
            "p": ctx.policies, "d": sorted(ctx.direct_codes), "o": ctx.obligation_owner,
            "g": [ctx.gap.get("gap_type"), ctx.gap.get("risk_rating"), ctx.gap.get("coverage_score")] if ctx.gap else None,
            "r": (resolve_regulator(regulator).code if resolve_regulator(regulator) else regulator),
            "v": [PROMPT_VERSION, self.analyzer.deployment, s.impact_review_confidence, s.impact_max_tasks_per_impact],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    # ------------------------------------------------------------------ analysis
    async def analyze(self, entry: DiffEntry, ctx: ImpactContext, regulator: str, document_title: str,
                      fingerprint: str) -> ImpactDraft:
        analysis: ChangeAnalysis | None = None
        error: str | None = None
        if entry.change_type in _NEEDS_LLM and not entry.minor:
            try:
                analysis = await self.analyzer.analyze(entry, ctx, regulator, document_title, resolve_regulator(regulator))
            except ChangeLLMError as exc:
                error = str(exc)
                log.warning("Change analysis failed; using rules only", extra={"impact_key": entry.key, "error": error})
        return self.assemble(entry, ctx, analysis, error, fingerprint, regulator)

    # ------------------------------------------------------------------ assembly
    def assemble(self, entry: DiffEntry, ctx: ImpactContext, analysis: ChangeAnalysis | None, error: str | None,
                 fingerprint: str, regulator: str) -> ImpactDraft:
        s = self.settings
        change_type, minor = entry.change_type, entry.minor
        if analysis:
            change_type = analysis.change_type
            if (not analysis.material and not entry.quantity_changes and not entry.modal_change
                    and change_type != ChangeType.NEW):
                minor, change_type = True, ChangeType.MODIFIED          # model says cosmetic and rules found no number change
        view = dataclasses.replace(entry, change_type=change_type, minor=minor)

        # which candidates really are affected
        if analysis:
            keep_controls = set(analysis.control_codes) | ctx.direct_codes
            keep_systems = set(analysis.system_codes) | ctx.direct_codes
            controls = [c for c in ctx.controls if c.code in keep_controls]
            systems = [x for x in ctx.systems if x.code in keep_systems]
        else:
            controls, systems = list(ctx.controls), list(ctx.systems)
        if minor:
            controls, systems = [], []                                   # wording only: nothing has to change
        excluded = [c.code for c in ctx.controls + ctx.systems if c not in controls and c not in systems]

        control_dicts = [{"code": c.code, "name": c.name, "owner": c.owner_function} for c in controls]
        system_dicts = [{"code": x.code, "name": x.name, "criticality": x.criticality, "owner": x.owner_function}
                        for x in sorted(systems, key=lambda x: -_CRITICALITY_RANK.get((x.criticality or "").upper(), -1))]

        teams: list[str] = []
        for t in [ctx.obligation_owner, *(c["owner"] for c in control_dicts), *(x["owner"] for x in system_dicts),
                  *(analysis.teams if analysis else [])]:
            if t and t.lower() not in {x.lower() for x in teams}:
                teams.append(t)
        primary_team = teams[0] if teams else remediation_service.DEFAULT_TEAM

        risk = risk_service.rate_impact(view, system_dicts, has_controls=bool(ctx.controls), gap=ctx.gap)
        tasks = remediation_service.build_tasks(
            view, control_dicts, system_dicts, ctx.policies, primary_team, risk.rating,
            analysis.actions if analysis else [], s.impact_max_tasks_per_impact)

        rec = entry.new or entry.old
        conf_parts = [analysis.confidence if analysis else (LLM_FAILED_CONFIDENCE if error else DETERMINISTIC_CONFIDENCE)]
        if rec and rec.confidence is not None:
            conf_parts.append(rec.confidence / 100.0)
        paired = entry.old is not None and entry.new is not None
        if paired and entry.similarity < 1.0:
            conf_parts.append(1.0 if entry.similarity >= 0.8 else entry.similarity + 0.2)
        confidence = round(max(0.0, min(conf_parts)), 2)
        needs_review = confidence < s.impact_review_confidence or error is not None or (paired and 0 < entry.similarity < 0.65)

        additional = list(entry.additional_changes)
        details = {
            "domain": entry.domain, "similarity": entry.similarity, "minor": minor,
            "quantity_changes": entry.quantity_changes,
            "modal_change": list(entry.modal_change) if entry.modal_change else None,
            "severity": [entry.severity_old, entry.severity_new], "risk_factors": risk.factors,
            "excluded_candidates": excluded, "policies": ctx.policies, "existing_gap": ctx.gap,
            "old_obligation_snapshot_id": entry.old.snapshot_id if entry.old else None,
            "old_obligation_id": entry.old.obligation_id if entry.old else None,
            "warnings": analysis.warnings if analysis else [], "llm_error": error,
            "regulator": regulator, "supported_regulator": resolve_regulator(regulator) is not None,
            "analysis_source": "gpt" if analysis else ("rules_fallback" if error else "rules"),
        }
        return ImpactDraft(
            entry=entry, change_type=change_type, clause_ref=entry.clause_ref,
            new_obligation_id=entry.new.obligation_id if entry.new else None,
            old_clause=entry.old.text if entry.old else "", new_clause=entry.new.text if entry.new else "",
            summary=analysis.summary if analysis else self._rule_summary(view), controls=control_dicts,
            systems=system_dicts, teams=teams or [primary_team], risk_rating=risk.rating, risk_score=risk.score,
            confidence=confidence, needs_review=needs_review, additional_changes=additional, tasks=tasks,
            details=details, fingerprint=fingerprint, model_used=self.analyzer.deployment if analysis else None,
            prompt_tokens=analysis.prompt_tokens if analysis else 0,
            completion_tokens=analysis.completion_tokens if analysis else 0, llm_calls=1 if analysis else 0,
        )

    @staticmethod
    def _rule_summary(entry: DiffEntry) -> str:
        change = remediation_service.describe_change(entry)
        if entry.change_type == ChangeType.REMOVED:
            return f"Obligation removed: {entry.old.text[:200]}"
        if entry.change_type == ChangeType.SEVERITY:
            return f"Severity of the obligation changed from {entry.severity_old} to {entry.severity_new}."
        if entry.minor:
            return "Wording updated; no number, deadline or mandatory language changed."
        if entry.change_type == ChangeType.NEW:
            return f"New obligation: {entry.new.text[:200]}"
        return f"Obligation changed{' (' + change + ')' if change else ''}: {entry.new.text[:200]}"
