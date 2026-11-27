"""GPT-4o gap analysis of one obligation against the assets Agent 3 mapped to it.

Split of responsibility:
  GPT   reads the text, compares parameters, proposes coverage / gap types / observation / recommendation
  rules decide Missing Control, Evidence Missing, failed tests, manual risk, caps, rating, confidence
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openai import APIError, BadRequestError

from services import control_quality
from services.gap_types import (LLM_GAP_TYPES, AssetView, Finding, GapType, LLMAssessment, ObligationView,
                                ParameterCheck, order_gaps)
from services.recommendation_service import build_recommendation, missing_control_text
from services.risk_scoring_service import score_risk
from settings import Settings

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "gap_assessment_prompt.txt"
PROMPT_VERSION = "gap-v1"
MAX_POLICIES, MAX_CONTROLS, MAX_SYSTEMS = 4, 4, 3
MAX_POLICY_CHARS = 1500
UNVERIFIED_CONFIDENCE_CAP = 0.6
DETERMINISTIC_CONFIDENCE = 0.90

GAP_SCHEMA = {
    "name": "gap_assessment",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["applicable_control_found", "parameters", "coverage", "gap_types", "primary_ref",
                     "supporting_refs", "observation", "recommendation", "confidence"],
        "properties": {
            "applicable_control_found": {"type": "boolean"},
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["parameter", "required", "actual", "met", "source_ref", "actual_quote"],
                    "properties": {
                        "parameter": {"type": "string"}, "required": {"type": "string"}, "actual": {"type": "string"},
                        "met": {"type": "boolean"}, "source_ref": {"type": "string"}, "actual_quote": {"type": "string"},
                    },
                },
            },
            "coverage": {"type": "number"},
            "gap_types": {"type": "array", "items": {"type": "string", "enum": LLM_GAP_TYPES}},
            "primary_ref": {"type": "string"},
            "supporting_refs": {"type": "array", "items": {"type": "string"}},
            "observation": {"type": "string"},
            "recommendation": {"type": "string"},
            "confidence": {"type": "number"},
        },
    },
}


class GapLLMError(Exception):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def select_assets(assets: list[AssetView]) -> list[AssetView]:
    """Best-relevance first, capped per type; DIRECT links before SUPPORTING. Assigns keys P1/C1/S1."""
    buckets = {"POLICY_SECTION": ("P", MAX_POLICIES), "CONTROL": ("C", MAX_CONTROLS), "SYSTEM": ("S", MAX_SYSTEMS)}
    chosen: list[AssetView] = []
    for target_type, (prefix, cap) in buckets.items():
        items = sorted((a for a in assets if a.target_type == target_type),
                       key=lambda a: (a.link_type != "DIRECT", -a.relevance, a.mapping_id))[:cap]
        for i, a in enumerate(items, 1):
            a.key = f"{prefix}{i}"
            chosen.append(a)
    return chosen


def render_user_message(ob: ObligationView, assets: list[AssetView]) -> str:
    lines = [
        "OBLIGATION",
        f"Regulator: {ob.regulator}", f"Document: {ob.document_title}",
        f"Clause: {ob.clause_ref or ob.citation or 'n/a'}", f"Type: {ob.obligation_type or 'n/a'}",
        f"Severity: {ob.severity or 'n/a'}", f"Owner function: {ob.owner_function or 'n/a'}",
        f"Requirement: {ob.text}", "",
    ]
    for title, kind in (("POLICIES", "POLICY_SECTION"), ("CONTROLS", "CONTROL"), ("SYSTEMS", "SYSTEM")):
        group = [a for a in assets if a.target_type == kind]
        lines.append(title if group else f"{title}: none")
        for a in group:
            if kind == "POLICY_SECTION":
                lines += [f"[{a.key}] {a.doc_code} section {a.section_ref or '-'} {a.heading or ''}".rstrip(),
                          f"Text: {a.text[:MAX_POLICY_CHARS]}"]
                if a.current_provision:
                    lines.append(f"Relevant provision: {a.current_provision}")
            elif kind == "CONTROL":
                lines += [f"[{a.key}] {a.code} {a.name}",
                          f"Description: {a.description or 'n/a'}",
                          f"Type: {a.control_type or 'n/a'}; frequency: {a.frequency or 'n/a'}; "
                          f"owner: {a.owner_function or 'n/a'}; automation: {a.automation_level or 'n/a'}",
                          f"Evidence source: {a.evidence_source or 'none recorded'}; last test: {a.test_result or 'n/a'}"]
            else:
                cats = ", ".join(a.data_categories) or "n/a"
                lines += [f"[{a.key}] {a.code} {a.name}", f"Description: {a.description or 'n/a'}; data: {cats}"]
        lines.append("")
    return "\n".join(lines).strip()


@dataclass
class Prepared:
    ob: ObligationView
    assets: list[AssetView]
    flags_by_control: dict[str, list[control_quality.QualityFlag]]
    fingerprint: str
    user_message: str = ""
    extra: dict = field(default_factory=dict)


class GapAnalyzer:
    def __init__(self, client, settings: Settings, prompt_path: Path = PROMPT_PATH):
        self.client = client
        self.settings = settings
        self.deployment = settings.azure_openai_deployment
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    # ---------------------------------------------------------------- prepare
    def rules_signature(self) -> str:
        s = self.settings
        return (f"{s.gap_param_mismatch_cap}|{s.gap_failed_test_cap}|{s.gap_escalate_high_severity}|"
                f"{s.gap_require_evidence}|{s.gap_review_confidence}")

    def prepare(self, ob: ObligationView, assets: list[AssetView], now: datetime) -> Prepared:
        chosen = select_assets(assets)
        flags = {c.code: control_quality.check_control(c, now, self.settings.gap_require_evidence)
                 for c in chosen if c.is_control}
        payload = {
            "o": [ob.text, ob.severity, ob.obligation_type, ob.owner_function, ob.confidence, ob.mapping_status],
            "a": [[a.mapping_id, a.key, a.code, a.review_status, round(a.relevance, 1), a.text, a.current_provision,
                   a.description, a.frequency, a.automation_level, a.evidence_source, a.test_result,
                   a.last_evidence_at.isoformat() if a.last_evidence_at else None] for a in chosen],
            "q": {code: sorted(f.gap_type for f in fl) for code, fl in flags.items()},
            "v": [PROMPT_VERSION, self.deployment, self.rules_signature()],
        }
        fp = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return Prepared(ob, chosen, flags, fp, render_user_message(ob, chosen))

    # ---------------------------------------------------------------- assess
    async def assess(self, prep: Prepared) -> Finding:
        assets = prep.assets
        controls = [a for a in assets if a.is_control]
        policies = [a for a in assets if a.target_type == "POLICY_SECTION"]
        base_details = {"assets": [{"key": a.key, "type": a.target_type, "code": a.code, "mapping_id": a.mapping_id,
                                    "relevance": a.relevance, "review_status": a.review_status} for a in assets]}

        if not controls:
            return self._missing_control(prep, policies, base_details, llm=None)

        llm = await self._call_llm(prep)
        if not llm.applicable_control_found:
            return self._missing_control(prep, policies, base_details, llm=llm)
        return self._build_finding(prep, llm, controls, base_details)

    def _missing_control(self, prep: Prepared, policies: list[AssetView], details: dict,
                         llm: LLMAssessment | None) -> Finding:
        ob = prep.ob
        observation, recommendation = missing_control_text(ob.text, ob.owner_function, ob.obligation_type)
        if llm and llm.observation:
            observation = f"{llm.observation.strip()} {observation}"
        gaps = [GapType.MISSING_CONTROL]
        risk = score_risk(0.0, ob.severity, gaps, has_control=False)
        conf = min(DETERMINISTIC_CONFIDENCE if llm is None else max(0.0, min(1.0, llm.confidence)),
                   (ob.confidence or 100.0) / 100.0)
        details = {**details, "risk_factors": risk.factors,
                   "note": "Policy text exists but no control" if policies else "No policy or control mapped"}
        mapping_id = policies[0].mapping_id if policies else None
        return Finding(
            obligation_id=ob.id, mapping_id=mapping_id, gap_type=GapType.MISSING_CONTROL, additional_gaps=[],
            risk_rating=risk.rating, risk_score=risk.score, coverage=0.0, observation=observation,
            recommendation=build_recommendation(recommendation, gaps, {}, ob.owner_function, risk.rating),
            confidence=round(conf, 2), owner_function=ob.owner_function, needs_review=True, details=details,
            fingerprint=prep.fingerprint, source_mapped_at=ob.mapped_at, model_used=self.deployment if llm else None,
            prompt_tokens=llm.prompt_tokens if llm else 0, completion_tokens=llm.completion_tokens if llm else 0,
            llm_calls=1 if llm else 0,
        )

    def _build_finding(self, prep: Prepared, llm: LLMAssessment, controls: list[AssetView], details: dict) -> Finding:
        s = self.settings
        ob = prep.ob
        by_key = {a.key: a for a in prep.assets}
        primary = by_key.get(llm.primary_ref or "")
        if primary is None or not primary.is_control:
            primary = controls[0]                       # best relevance, since select_assets sorted them

        flags = prep.flags_by_control.get(primary.code, [])
        reasons = control_quality.summarise(flags)
        coverage = max(0.0, min(100.0, llm.coverage))
        gaps = set(llm.gap_types) | set(reasons)
        mismatches = [p for p in llm.parameters if not p.met]
        adjustments: list[str] = []

        if mismatches:
            gaps.add(GapType.PARTIAL_COVERAGE)
            if coverage > s.gap_param_mismatch_cap:
                adjustments.append(f"Coverage capped {coverage:.0f} -> {s.gap_param_mismatch_cap:.0f}: "
                                   f"{mismatches[0].parameter} not met.")
                coverage = s.gap_param_mismatch_cap
        if primary.test_result == "FAILED" and coverage > s.gap_failed_test_cap:
            adjustments.append(f"Coverage capped {coverage:.0f} -> {s.gap_failed_test_cap:.0f}: control failed its test.")
            coverage = s.gap_failed_test_cap
        if not gaps and coverage <= 80:
            gaps.add(GapType.PARTIAL_COVERAGE)           # stay consistent: below 80% is never "no gap"
        ordered = order_gaps(gaps)
        primary_gap = ordered[0] if ordered else GapType.NO_GAP

        risk = score_risk(coverage, ob.severity, ordered, has_control=True,
                          escalate_high_severity=s.gap_escalate_high_severity)

        unverified = [p for p in llm.parameters if not p.verified]
        conf = min(max(0.0, min(1.0, llm.confidence)), (ob.confidence or 100.0) / 100.0, primary.relevance / 100.0)
        if unverified:
            conf = min(conf, UNVERIFIED_CONFIDENCE_CAP)
        conf = round(conf, 2)

        observation = llm.observation.strip()
        for gap in (GapType.CONTROL_INEFFECTIVE, GapType.EVIDENCE_MISSING, GapType.MANUAL_PROCESS_RISK):
            if gap in reasons and gap not in llm.gap_types:
                observation += " " + " ".join(reasons[gap])
        recommendation = build_recommendation(llm.recommendation, ordered, reasons,
                                              ob.owner_function or primary.owner_function, risk.rating)
        details = {
            **details,
            "primary_control": primary.code,
            "parameters": [p.__dict__ for p in llm.parameters],
            "quality_flags": reasons,
            "risk_factors": risk.factors,
            "adjustments": adjustments,
            "warnings": llm.warnings,
            "llm_coverage": llm.coverage,
            "supporting_refs": llm.supporting_refs,
        }
        return Finding(
            obligation_id=ob.id, mapping_id=primary.mapping_id,
            gap_type=primary_gap, additional_gaps=ordered[1:], risk_rating=risk.rating, risk_score=risk.score,
            coverage=round(coverage, 2), observation=observation, recommendation=recommendation, confidence=conf,
            owner_function=ob.owner_function or primary.owner_function,
            needs_review=conf < s.gap_review_confidence or bool(unverified), details=details,
            fingerprint=prep.fingerprint, source_mapped_at=ob.mapped_at, model_used=self.deployment,
            prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens, llm_calls=1,
        )

    # ---------------------------------------------------------------- llm
    async def _call_llm(self, prep: Prepared) -> LLMAssessment:
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prep.user_message}]
        prompt_tokens = completion_tokens = 0
        last_error = "unknown"
        for attempt in (1, 2):                            # one retry for malformed / truncated JSON
            try:
                resp = await self.client.chat.completions.create(
                    model=self.deployment, messages=messages, temperature=0,
                    max_tokens=self.settings.gap_max_completion_tokens,
                    response_format={"type": "json_schema", "json_schema": GAP_SCHEMA},
                )
            except BadRequestError as exc:
                raise GapLLMError(f"bad_request: {exc.message}"[:500]) from exc
            except APIError as exc:
                raise GapLLMError(f"api_error: {exc}"[:500]) from exc
            if resp.usage:
                prompt_tokens += resp.usage.prompt_tokens
                completion_tokens += resp.usage.completion_tokens
            try:
                raw = json.loads(resp.choices[0].message.content or "")
                result = self.validate(raw, prep)
                result.prompt_tokens, result.completion_tokens = prompt_tokens, completion_tokens
                return result
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                last_error = f"invalid_json: {exc}"[:300]
                log.warning("Invalid gap JSON", extra={"obligation_id": prep.ob.id, "attempt": attempt})
        raise GapLLMError(last_error)

    @staticmethod
    def validate(raw: dict, prep: Prepared) -> LLMAssessment:
        """Coerce the model output and check every quote really appears in the text it was shown."""
        corpus = {a.key: _norm(a.evidence_text) for a in prep.assets}
        everything = " ".join(corpus.values())
        warnings: list[str] = []
        params: list[ParameterCheck] = []
        for p in raw["parameters"]:
            quote = (p.get("actual_quote") or "").strip()
            ref = (p.get("source_ref") or "").strip()
            haystack = corpus.get(ref, everything)
            verified = bool(quote) and _norm(quote) in haystack
            if not verified and (quote or p.get("met")):
                warnings.append(f"Unverified evidence for '{p.get('parameter')}'")
            elif not quote and not p.get("met"):
                verified = True                           # "Not stated" needs no quote
            params.append(ParameterCheck(parameter=p["parameter"], required=p["required"], actual=p["actual"],
                                         met=bool(p["met"]), source_ref=ref, actual_quote=quote, verified=verified))
        gap_types = [g for g in raw["gap_types"] if g in LLM_GAP_TYPES]
        return LLMAssessment(
            applicable_control_found=bool(raw["applicable_control_found"]), parameters=params,
            coverage=float(raw["coverage"]), gap_types=gap_types, primary_ref=(raw.get("primary_ref") or "").strip() or None,
            supporting_refs=[r for r in raw.get("supporting_refs", []) if r in corpus],
            observation=(raw["observation"] or "").strip(), recommendation=(raw["recommendation"] or "").strip(),
            confidence=float(raw["confidence"]), warnings=warnings,
        )
