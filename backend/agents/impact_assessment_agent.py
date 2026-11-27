"""Agent 5: Regulatory Change Impact & Remediation Agent.

Workflow
  1. previous regulation = obligations Agent 2 saved before replacing them (or another document you name);
     new regulation = the document's current obligations
  2. diff: match old and new clauses, classify each change (new / modified / removed / severity / retention / reporting / security)
  3. per change: candidate controls, systems, policies and teams from Agent 3's mappings and the registers,
     Agent 4's current gap, then GPT-4o confirms what is really affected and proposes remediation
  4. rules rate the risk (matrix) and build the remediation tasks; unchanged changes are skipped by fingerprint
  5. store impacts and tasks (task status survives re-runs), overall document risk, audit log
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from agents.errors import DocumentNotFoundError, DocumentNotReadyError, InvalidComparisonError
from agents.gap_assessment_agent import MAPPING_DONE
from repositories import (AuditRepository, DocumentRepository, GapRepository, ImpactRepository, MappingRepository,
                          ObligationRepository, RemediationRepository)
from schemas import GapUsageOut, ImpactAnalysisSummary, ImpactReport
from services import impact_presenter as present
from services.gap_types import Risk
from services.impact_analysis_service import (ImpactAnalysisService, records_from_obligations, records_from_versions)
from services.impact_types import DiffEntry, ImpactDraft, ObligationRec
from services.regulation_diff_service import diff
from services.risk_service import overall_risk
from settings import Settings

log = logging.getLogger(__name__)

NOT_READY_STATUSES = {"MISSING", "HEALING"}
RATING_ORDER = [Risk.CRITICAL, Risk.HIGH, Risk.MEDIUM, Risk.LOW]


class ImpactAssessmentAgent:
    def __init__(self, session: AsyncSession, documents: DocumentRepository, obligations: ObligationRepository,
                 mappings: MappingRepository, gaps: GapRepository, impacts: ImpactRepository,
                 remediation: RemediationRepository, audit: AuditRepository, service: ImpactAnalysisService,
                 settings: Settings):
        self.session = session
        self.documents = documents
        self.obligations = obligations
        self.mappings = mappings
        self.gaps = gaps
        self.impacts = impacts
        self.remediation = remediation
        self.audit = audit
        self.service = service
        self.settings = settings

    # ================================================================== run
    async def run(self, document_id: int, force: bool = False,
                  compare_to_document_id: int | None = None) -> ImpactAnalysisSummary:
        started = time.perf_counter()
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        if (doc.status or "").upper() in NOT_READY_STATUSES:
            raise DocumentNotReadyError(f"Document {doc.doc_code} is {doc.status}; wait for Agent 1 to restore it")
        other = None
        if compare_to_document_id is not None:
            if compare_to_document_id == document_id:
                raise InvalidComparisonError("A document cannot be compared with itself")
            other = await self.documents.get_by_id(compare_to_document_id)
            if other is None:
                raise DocumentNotFoundError(f"Comparison document {compare_to_document_id} not found")

        summary = ImpactAnalysisSummary(document_id=doc.id, doc_code=doc.doc_code, regulator=doc.regulator,
                                        status="COMPLETED", current_version=doc.version_tag)
        await self.audit.log("IMPACT_ANALYSIS_STARTED", doc.doc_code, {
            "document_id": doc.id, "force": force, "compare_to_document_id": compare_to_document_id})

        # ---- 1. both sides of the comparison
        new_obls = list(await self.obligations.list_by_document(document_id))
        if not new_obls:
            summary.status = "NO_OBLIGATIONS"
            summary.warnings.append("No obligations extracted yet; run Agent 2 first.")
            return await self._finish(summary, doc, started, persist_run=True)
        ready_ids = [o.id for o in new_obls if o.mapping_status in MAPPING_DONE]
        new_assets = await self.mappings.load_for_obligations(ready_ids)
        new_recs = records_from_obligations(new_obls, new_assets)

        if other is not None:
            other_obls = list(await self.obligations.list_by_document(other.id))
            other_assets = await self.mappings.load_for_obligations([o.id for o in other_obls])
            old_recs: list[ObligationRec] | None = records_from_obligations(other_obls, other_assets)
            summary.baseline = f"document {other.doc_code} ({other.version_tag})"
            summary.previous_version = other.version_tag
        else:
            snapshot, previous_tag, replaced_by = await self.impacts.load_previous_version(document_id)
            summary.previous_version = previous_tag
            if snapshot:
                old_recs = records_from_versions(snapshot)
                summary.baseline = "previous version of this document" + (f" (replaced by {replaced_by})" if replaced_by else "")
            elif self.settings.impact_first_version_as_new:
                old_recs = []
                summary.baseline = "none (first version: every obligation is new)"
            else:
                old_recs = None
        if old_recs is None:
            summary.status = "NO_PREVIOUS_VERSION"
            summary.warnings.append("No previous version of this document is stored, so there is nothing to compare.")
            return await self._finish(summary, doc, started, persist_run=True)

        # ---- 2. diff
        entries = diff(old_recs, new_recs, self.settings.impact_match_threshold)
        seen: set[str] = set()                         # identical old/new wording twice = one change
        entries = [e for e in entries if not (e.key in seen or seen.add(e.key))]
        if not entries:
            summary.status = "NO_CHANGES"
            await self._persist(document_id, [], set(), {}, summary)
            return await self._finish(summary, doc, started, persist_run=True)

        pending_entries = [e for e in entries if e.new is not None and e.new.mapping_status not in MAPPING_DONE]
        summary.pending_mapping = [e.new.obligation_id for e in pending_entries]
        work = [e for e in entries if e not in pending_entries]

        # ---- 3. context and fingerprints
        control_codes, system_codes = [], []
        for e in work:
            c, s = self.service.candidate_codes(e)
            control_codes += c
            system_codes += s
        control_codes = list(dict.fromkeys(control_codes))
        controls = await self.mappings.controls_by_codes(control_codes)
        linked = await self.mappings.linked_system_codes(list(controls))
        all_system_codes = list(dict.fromkeys(system_codes + [s for codes in linked.values() for s in codes]))
        systems = await self.mappings.systems_by_codes(all_system_codes)
        gaps = await self.gaps.summaries([e.new.obligation_id for e in work if e.new is not None])
        known = await self.impacts.fingerprints(document_id)
        await self.session.commit()                    # release the connection while GPT works

        regulator = doc.regulator or ""
        todo: list[tuple[DiffEntry, object, str]] = []
        relink: dict[str, int | None] = {}
        for e in work:
            ctx = self.service.build_context(e, controls, systems, linked, gaps.get(e.new.obligation_id) if e.new else None)
            fp = self.service.fingerprint(e, ctx, regulator)
            if not force and known.get(e.key) == fp:
                summary.unchanged += 1
                relink[e.key] = e.new.obligation_id if e.new else None
            else:
                todo.append((e, ctx, fp))

        # ---- 4. GPT-4o + rules, bounded concurrency
        sem = asyncio.Semaphore(self.settings.impact_concurrency)

        async def one(entry: DiffEntry, ctx, fp: str) -> ImpactDraft:
            async with sem:
                return await self.service.analyze(entry, ctx, regulator, doc.title or doc.doc_code, fp)

        drafts = list(await asyncio.gather(*(one(*t) for t in todo)))
        summary.analyzed = len(drafts)
        summary.rules_only = sum(1 for d in drafts if d.details.get("llm_error"))
        if drafts and any(d.llm_calls for d in drafts):
            summary.usage = GapUsageOut(model=self.service.analyzer.deployment, llm_calls=sum(d.llm_calls for d in drafts),
                                        prompt_tokens=sum(d.prompt_tokens for d in drafts),
                                        completion_tokens=sum(d.completion_tokens for d in drafts))

        # ---- 5. store
        keep_keys = {e.key for e in entries}
        summary.removed_stale = await self._persist(document_id, drafts, keep_keys, relink, summary)

        if summary.pending_mapping or summary.rules_only:
            summary.status = "PARTIAL"
        if summary.pending_mapping:
            summary.warnings.append(f"{len(summary.pending_mapping)} changed obligation(s) are still being mapped by Agent 3; "
                                    "they are analysed when mapping finishes.")
        if summary.rules_only:
            summary.warnings.append(f"{summary.rules_only} change(s) were analysed by rules only because GPT-4o failed.")
        return await self._finish(summary, doc, started, persist_run=True)

    # ================================================================== reads
    async def report(self, document_id: int, risk_rating: str | None = None, change_type: str | None = None) -> ImpactReport:
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        run = await self.impacts.get_run(document_id)
        impacts = await self._impacts_out(document_id, risk_rating, change_type)
        report = ImpactReport(document_id=doc.id, doc_code=doc.doc_code, regulator=doc.regulator,
                              current_version=doc.version_tag, stats=present.build_stats(impacts), impacts=impacts)
        if run:
            report.status, report.baseline, report.previous_version = run.status, run.baseline, run.previous_version
            report.current_version = run.current_version or doc.version_tag
            report.overall_risk_rating = run.overall_risk_rating
            report.overall_risk_score = float(run.overall_risk_score) if run.overall_risk_score is not None else None
            report.summary, report.pending_mapping = run.summary, list(run.pending_mapping or [])
            report.analyzed_at = run.updated_at
        return report

    async def tasks(self, document_id: int, status: str | None = None, priority: str | None = None,
                    owner_team: str | None = None):
        doc = await self.documents.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(f"Regulatory document {document_id} not found")
        rows = await self.remediation.list_for_document(document_id, status, priority, owner_team)
        return present.build_task_report(doc.id, doc.doc_code, [present.to_task_out(t, i) for t, i in rows])

    # ================================================================== helpers
    async def _impacts_out(self, document_id: int, risk_rating: str | None = None, change_type: str | None = None):
        impacts = await self.impacts.list_for_document(document_id, risk_rating, change_type)
        by_impact = present.group_tasks(await self.remediation.list_for_document(document_id))
        return [present.to_impact_out(i, by_impact.get(i.id, [])) for i in impacts]

    async def _persist(self, document_id: int, drafts: list[ImpactDraft], keep_keys: set[str],
                       relink: dict[str, int | None], summary: ImpactAnalysisSummary) -> int:
        await self.impacts.lock_document(document_id)
        ids = [d.new_obligation_id for d in drafts if d.new_obligation_id] + [o for o in relink.values() if o]
        alive = await self.obligations.existing_ids(ids)        # a re-extraction may have replaced them meanwhile

        rows = [{
            "document_id": document_id, "impact_key": d.entry.key, "change_type": d.change_type,
            "old_clause": d.old_clause or None, "new_clause": d.new_clause or None,
            "affected_control": d.controls[0]["name"] if d.controls else None,
            "affected_system": d.systems[0]["name"] if d.systems else None,
            "affected_team": d.teams[0] if d.teams else None, "risk_rating": d.risk_rating,
            "remediation_action": d.tasks[0].name if d.tasks else None, "confidence_score": d.confidence,
            "clause_ref": d.clause_ref, "new_obligation_id": d.new_obligation_id if d.new_obligation_id in alive else None,
            "risk_score": d.risk_score, "summary": d.summary, "additional_changes": d.additional_changes,
            "affected_controls": d.controls, "affected_systems": d.systems, "affected_teams": d.teams,
            "needs_review": d.needs_review, "details": d.details, "fingerprint": d.fingerprint, "model_used": d.model_used,
        } for d in drafts]
        key_to_id = await self.impacts.upsert_impacts(rows)
        await self.remediation.sync_tasks({
            key_to_id[d.entry.key]: [{"task_name": t.name, "owner_team": t.owner_team, "priority": t.priority,
                                      "due_days": t.due_days, "task_key": t.key, "detail": t.detail or None}
                                     for t in d.tasks] for d in drafts})
        await self.impacts.relink(document_id, {k: (o if o in alive else None) for k, o in relink.items()})
        removed = await self.impacts.delete_missing(document_id, keep_keys)
        await self.session.commit()
        return removed

    async def _finish(self, summary: ImpactAnalysisSummary, doc, started: float, persist_run: bool) -> ImpactAnalysisSummary:
        impacts = await self._impacts_out(doc.id)
        summary.impacts = impacts
        summary.stats = present.build_stats(impacts)
        if impacts:
            summary.overall_risk_rating, summary.overall_risk_score = overall_risk([i.risk_rating for i in impacts])
        elif summary.status in ("NO_CHANGES", "COMPLETED"):
            summary.overall_risk_rating, summary.overall_risk_score = Risk.LOW, 0.0
        summary.summary = self._summary_text(summary)
        summary.duration_ms = int((time.perf_counter() - started) * 1000)

        if persist_run:
            await self.impacts.upsert_run({
                "document_id": doc.id, "status": summary.status, "baseline": summary.baseline,
                "previous_version": summary.previous_version, "current_version": summary.current_version,
                "total_changes": summary.stats.total, "by_change_type": summary.stats.by_change_type,
                "by_risk": summary.stats.by_risk, "overall_risk_score": summary.overall_risk_score,
                "overall_risk_rating": summary.overall_risk_rating, "summary": summary.summary,
                "pending_mapping": summary.pending_mapping,
                "model_used": summary.usage.model if summary.usage else self.service.analyzer.deployment})
        await self.audit.log("IMPACT_ANALYSIS_COMPLETED", doc.doc_code, {
            "document_id": doc.id, "status": summary.status, "changes": summary.stats.total, "analyzed": summary.analyzed,
            "unchanged": summary.unchanged, "overall_risk": summary.overall_risk_rating})
        await self.session.commit()
        log.info("Impact analysis finished", extra={"document_id": doc.id, "status": summary.status,
                                                    "changes": summary.stats.total, "analyzed": summary.analyzed,
                                                    "unchanged": summary.unchanged})
        return summary

    @staticmethod
    def _summary_text(s: ImpactAnalysisSummary) -> str | None:
        if s.status == "NO_OBLIGATIONS":
            return "No obligations have been extracted for this document."
        if s.status == "NO_PREVIOUS_VERSION":
            return "No previous version is stored, so no comparison was possible."
        if s.status == "NO_CHANGES":
            return f"No obligation changed compared with {s.baseline or 'the previous version'}."
        if not s.impacts:
            return None
        by_risk = ", ".join(f"{s.stats.by_risk[r]} {r}" for r in RATING_ORDER if s.stats.by_risk.get(r))
        top = s.impacts[0]
        controls = {c["code"] for i in s.impacts for c in i.affected_controls}
        systems = {x["code"] for i in s.impacts for x in i.affected_systems}
        teams = {t for i in s.impacts for t in i.affected_teams}
        return (f"{s.stats.total} change(s) vs {s.baseline or 'the previous version'}: {by_risk}. "
                f"Overall risk {s.overall_risk_rating} ({s.overall_risk_score}). Affects {len(controls)} control(s), "
                f"{len(systems)} system(s) and {len(teams)} team(s); {s.stats.tasks_open} open remediation task(s). "
                f"Highest risk: {top.change_type} at clause {top.clause_ref or 'n/a'}"
                f"{' (' + top.summary + ')' if top.summary else ''}.")
