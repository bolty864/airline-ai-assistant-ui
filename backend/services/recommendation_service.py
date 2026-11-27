"""Turns gaps into an actionable recommendation. GPT supplies the policy/control-specific fix;
rules add the standard remediation for missing control, evidence, effectiveness and manual risk."""
from __future__ import annotations

from services.gap_types import GapType, Risk

TARGET_DAYS = {Risk.CRITICAL: 15, Risk.HIGH: 30, Risk.MEDIUM: 60, Risk.LOW: 90}


def _owner(owner: str | None) -> str:
    return owner or "the accountable function"


def deterministic_actions(gaps: list[str], flag_reasons: dict[str, list[str]], owner: str | None) -> list[str]:
    o = _owner(owner)
    actions: list[str] = []
    if GapType.CONTROL_INEFFECTIVE in gaps:
        actions.append(f"Root-cause the failed control test and re-test; {o} to remediate before the next test cycle.")
    if GapType.EVIDENCE_MISSING in gaps:
        actions.append(f"{o} to define the evidence source and retain periodic evidence for audit.")
    if GapType.MANUAL_PROCESS_RISK in gaps:
        actions.append("Automate the manual step, or add maker-checker review and a completion checklist until it is automated.")
    return actions


def missing_control_text(obligation_text: str, owner: str | None, obligation_type: str | None) -> tuple[str, str]:
    o = _owner(owner)
    kind = f" ({obligation_type})" if obligation_type else ""
    observation = (f"No control in the enterprise register addresses this obligation{kind}. "
                   f"Compliance cannot currently be demonstrated.")
    recommendation = (f"Design and implement a control for this requirement, owned by {o}: define the control "
                      f"objective, frequency, evidence and testing, and update the relevant policy.")
    return observation, recommendation


def build_recommendation(llm_recommendation: str, gaps: list[str], flag_reasons: dict[str, list[str]],
                         owner: str | None, rating: str) -> str:
    parts = [llm_recommendation.strip()] if llm_recommendation.strip() else []
    parts += deterministic_actions(gaps, flag_reasons, owner)
    if gaps and gaps != [GapType.NO_GAP]:
        parts.append(f"Target completion: {TARGET_DAYS[rating]} days.")
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts)
