"""Remediation tasks for a change: rule-based baseline, merged with the specific actions GPT-4o proposed.

Priority is the impact's risk rating; the due date follows from it (same targets as Agent 4's recommendations).
"""
from __future__ import annotations

import hashlib
import re

from services.gap_types import Risk
from services.impact_types import ChangeType, DiffEntry, Domain, TaskDraft
from services.regulation_diff_service import canon

DUE_DAYS = {Risk.CRITICAL: 15, Risk.HIGH: 30, Risk.MEDIUM: 60, Risk.LOW: 90}
RETEST_EXTRA_DAYS = 30
DEFAULT_TEAM = "Compliance Office"
_SIMILAR = 0.75     # overlap of the shorter task name with the longer one


def describe_change(entry: DiffEntry) -> str:
    """'3 years -> 5 years' for number changes, else ''."""
    parts = []
    for q in entry.quantity_changes:
        old = " / ".join(q["old"]) or "none"
        new = " / ".join(q["new"]) or "none"
        parts.append(f"{old} {q['unit']}s -> {new} {q['unit']}s")
    return "; ".join(parts)


def _key(name: str, owner: str) -> str:
    return hashlib.md5(f"{canon(name)}|{canon(owner)}".encode()).hexdigest()


def _similar(a: str, b: str) -> bool:
    ta, tb = set(canon(a).split()), set(canon(b).split())
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= _SIMILAR


def _clean(name: str, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", name or "").strip().rstrip(".")[:limit]


def build_tasks(entry: DiffEntry, controls: list[dict], systems: list[dict], policies: list[dict], primary_team: str,
                rating: str, llm_actions: list[dict], max_tasks: int = 5) -> list[TaskDraft]:
    base = DUE_DAYS[rating]
    ct, domain = entry.change_type, entry.domain
    change = describe_change(entry)
    suffix = f" ({change})" if change else ""
    ctrl = controls[0] if controls else None
    ctrl_owner = (ctrl or {}).get("owner") or primary_team
    rules: list[tuple[str, str, str, int]] = []      # (name, owner, detail, due_days)

    if ct == ChangeType.REMOVED:
        for c in controls[:2]:
            rules.append((f"Review {c['name']} for retirement or reduced scope", c.get("owner") or primary_team,
                          "The obligation it supported was removed. Confirm no other obligation depends on the control "
                          "before changing it.", base))
        if policies:
            rules.append((f"Update {policies[0]['name']} to remove the withdrawn requirement", primary_team, "", base))
    elif ct == ChangeType.SEVERITY:
        rules.append((f"Re-prioritise testing and ownership under the new {entry.severity_new} severity"
                      f"{' for ' + ctrl['name'] if ctrl else ''}", ctrl_owner, "", base))
    else:
        if ctrl is None:
            rules.append((f"Design and implement a control for: {_clean(entry.new.text, 120)}", primary_team,
                          "No existing control covers this requirement.", base))
        elif ct == ChangeType.NEW:
            rules.append((f"Extend {ctrl['name']} to cover the new requirement", ctrl_owner, "", base))
        else:
            lead = {Domain.RETENTION: "Update retention configuration of", Domain.REPORTING: "Update reporting procedure of",
                    Domain.SECURITY: "Update security settings of"}.get(domain, "Update")
            rules.append((f"{lead} {ctrl['name']} to meet the revised requirement{suffix}", ctrl_owner, "", base))
        for s in systems[:2]:
            if (s.get("criticality") or "").upper() in ("CRITICAL", "HIGH") or domain != Domain.OTHER:
                rules.append((f"Reconfigure and validate {s['name']} against the revised requirement{suffix}",
                              s.get("owner") or primary_team, "", base))
        if policies:
            rules.append((f"Revise {policies[0]['name']} to reflect the revised requirement{suffix}", primary_team, "", base))
        if ctrl is not None:
            rules.append((f"Re-test {ctrl['name']} and retain evidence of compliance", ctrl_owner, "",
                          min(base + RETEST_EXTRA_DAYS, 120)))

    drafts: list[TaskDraft] = []
    for action in llm_actions:                                       # specific actions first
        name = _clean(action.get("task_name", ""))
        if name:
            _add(drafts, name, _clean(action.get("owner_team", ""), 100) or primary_team, rating, base,
                 _clean(action.get("detail", ""), 500))
    for name, owner, detail, days in rules:                          # then the baseline, skipping near-duplicates
        if not any(_similar(name, d.name) for d in drafts):
            _add(drafts, _clean(name), owner, rating, days, detail)
    return drafts[:max_tasks]


def _add(drafts: list[TaskDraft], name: str, owner: str, priority: str, days: int, detail: str) -> None:
    key = _key(name, owner)
    if not any(d.key == key for d in drafts):
        drafts.append(TaskDraft(name=name, owner_team=owner, priority=priority, due_days=days, key=key, detail=detail))
