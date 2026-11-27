"""ORM rows -> API schemas, and the roll-up statistics for Agent 5."""
from __future__ import annotations

from collections import Counter

from models import RegulationChangeImpact, RemediationTask
from schemas import ChangeImpactOut, ImpactStats, RemediationTaskOut, TaskReport


def to_task_out(t: RemediationTask, i: RegulationChangeImpact) -> RemediationTaskOut:
    return RemediationTaskOut(
        id=t.id, impact_id=t.impact_id, task_name=t.task_name, owner_team=t.owner_team, priority=t.priority,
        due_days=t.due_days, status=t.status or "OPEN", detail=t.detail, change_type=i.change_type,
        clause_ref=i.clause_ref, risk_rating=i.risk_rating, created_at=t.created_at)


def to_impact_out(i: RegulationChangeImpact, tasks: list[RemediationTaskOut]) -> ChangeImpactOut:
    return ChangeImpactOut(
        id=i.id, document_id=i.document_id, change_type=i.change_type, old_clause=i.old_clause or None,
        new_clause=i.new_clause or None, affected_control=i.affected_control, affected_system=i.affected_system,
        affected_team=i.affected_team, risk_rating=i.risk_rating, remediation_action=i.remediation_action,
        confidence_score=float(i.confidence_score or 0), clause_ref=i.clause_ref,
        risk_score=float(i.risk_score) if i.risk_score is not None else None, summary=i.summary,
        additional_changes=list(i.additional_changes or []), affected_controls=list(i.affected_controls or []),
        affected_systems=list(i.affected_systems or []), affected_teams=list(i.affected_teams or []),
        needs_review=i.needs_review, tasks=tasks, details=i.details or {}, assessed_at=i.updated_at or i.created_at)


def group_tasks(rows: list[tuple[RemediationTask, RegulationChangeImpact]]) -> dict[int, list[RemediationTaskOut]]:
    out: dict[int, list[RemediationTaskOut]] = {}
    for task, impact in rows:
        out.setdefault(impact.id, []).append(to_task_out(task, impact))
    return out


def build_stats(impacts: list[ChangeImpactOut]) -> ImpactStats:
    tasks = [t for i in impacts for t in i.tasks]
    return ImpactStats(
        total=len(impacts), by_change_type=dict(Counter(i.change_type for i in impacts)),
        by_risk=dict(Counter(i.risk_rating for i in impacts)), needs_review=sum(1 for i in impacts if i.needs_review),
        tasks_total=len(tasks), tasks_open=sum(1 for t in tasks if t.status in ("OPEN", "IN_PROGRESS")))


def build_task_report(document_id: int, doc_code: str, tasks: list[RemediationTaskOut]) -> TaskReport:
    return TaskReport(
        document_id=document_id, doc_code=doc_code, total=len(tasks), by_status=dict(Counter(t.status for t in tasks)),
        by_priority=dict(Counter(t.priority or "n/a" for t in tasks)),
        by_team=dict(Counter(t.owner_team or "unassigned" for t in tasks)), tasks=tasks)
