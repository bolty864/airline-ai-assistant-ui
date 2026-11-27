# AeroComply AI backend: Agents 1 to 5

One FastAPI service, one Postgres database, one set of Azure settings.

```
Agent 1: Monitoring & Self-Healing      Agent 2: Obligation Extraction          Agent 3: Policy & Control Mapping
crawl / ingest / watchdog        ──▶    PDF/DOCX/HTML → clauses → GPT-4o  ──▶   policies / controls / systems
regulatory_documents + Blob             compliance_obligations (PENDING)        obligation_mappings, v_obligation_impact
```
```
Agent 4: Compliance Gap Assessment
obligations + mappings + control register ──▶ compliance_gap_assessments (risk, coverage, recommendation)
```
```
Agent 5: Regulatory Change Impact & Remediation
previous version + new version ──▶ regulation_change_impacts, remediation_tasks, regulation_impact_runs
```
`agents/pipeline.py` chains them: every NEW, UPDATED or HEALED document goes to Agent 2, then Agent 3, then Agent 4, then Agent 5.

## Setup
```bash
cd backend
pip install -r requirements.txt
copy .env.example .env                 # Azure OpenAI, Postgres, Blob
psql "$DATABASE_URL" -f sql/001_base_schema.sql                    # safe on the existing schema
psql "$DATABASE_URL" -f sql/002_agent3_policy_control_mapping.sql  # REQUIRED (Agent 3 tables, mapping_status)
psql "$DATABASE_URL" -f sql/003_agent4_gap_assessment.sql          # REQUIRED (gap table + control evidence columns)
psql "$DATABASE_URL" -f sql/004_agent5_impact_assessment.sql        # REQUIRED (impact + task tables, version history)
python run.py                        # http://localhost:8000/docs  (use run.py on Windows, not plain uvicorn)
```

## Demo script (works offline with LOCAL_STORAGE_ROOT=./data/blobs)
```bash
curl -X POST localhost:8000/api/mapping/ingest            # Agent 3 indexes policies, controls, systems

curl -X POST localhost:8000/api/ingest -H "content-type: application/json" -d '{
  "doc_code": "DGCA_CAR_API_Retention", "filename": "DGCA_CAR_API_Retention.pdf", "regulator": "DGCA",
  "title": "CAR Section 3 Series M Part IV - API",
  "source_url": "http://localhost:8000/api/demo/sources/DGCA_CAR_API_Retention.pdf", "wait": true }'
# → NEW_DOC, 7 obligations extracted, mapped to Passenger Data Policy 4.1 ("3 years"), CTRL-001, APIS Scheduler

curl -X POST localhost:8000/api/demo/simulate-delete -H "content-type: application/json" -d '{"doc_code":"DGCA_CAR_API_Retention"}'
# within 5 s: MISSING_DETECTED → SELF_HEALED → OBLIGATIONS_EXTRACTED → OBLIGATIONS_MAPPED
curl "localhost:8000/api/audit-logs?doc_code=DGCA_CAR_API_Retention"
```
`/api/demo/sources/` is a stand-in regulator website, so the self-heal demo does not depend on dgca.gov.in being up.

## Agent 1: what changed when merging
| Original | Merged | Why |
|---|---|---|
| Own GPT-4o-mini extraction on the first 12k chars | Hands off to Agent 2 (clause-level GPT-4o) then Agent 3 | One extraction path; long CARs are no longer truncated |
| psycopg2 + sync Blob calls inside async code | Async SQLAlchemy, Blob calls in threads | Sync calls blocked the event loop and every request with it |
| Watchdog downloads every file every 5 s to hash it | sha256 stored in blob metadata on upload, compared on scan | A 5 s scan no longer re-downloads the whole repository |
| A failed heal left the doc HEALING forever (never retried) | Becomes MISSING, retried after HEAL_RETRY_SECONDS; stuck HEALING is recovered | No silent dead documents |
| Storage outage would look like "all files missing" | Blob check errors skip the doc instead of healing | No mass re-download during an outage |
| Healed file different from the stored hash | Treated as a new version: DOC_UPDATED + version bump | Regulator changes are not hidden inside a heal |
| doc_code from link text only | Link text + URL hash | Many DGCA links say "View"; they overwrote each other |
| `verify=False` always | REGULATOR_TLS_VERIFY (default true) | Opt-in only |
| `.pdf` assumed | Format detected from content | DGCA viewer links often return HTML |
| Updates kept version v1.0 | v1.0 → v1.1 on DOC_UPDATED | Version lineage for Agent 7 |
| APScheduler job | asyncio loop with a scan lock | No overlapping scans with `/api/watchdog/scan` |

Endpoints are unchanged: `/api/health`, `/api/documents`, `/api/documents/{doc_code}/obligations`, `/api/audit-logs`,
`/api/ingest` (+ optional `"wait": true`), `/api/crawl/trigger`, `/api/demo/simulate-delete`, `/api/watchdog/scan`.
Audit events: `NEW_DOC`, `DOC_UPDATED`, `DOC_UNCHANGED`, `MISSING_DETECTED`, `SELF_HEALED`, `HEAL_FAILED`, `DEMO_BLOB_DELETED`.

The DGCA crawler needs Playwright (`pip install playwright && playwright install chromium`). Without it, the crawl
reports the DGCA crawler as skipped instead of failing. CERT-In uses plain httpx.

## Agent 2: how it works
| Step | What happens | Why |
|---|---|---|
| 1-2 | Load `regulatory_documents` row, read `blob_path` from storage, sha256 check | Hash mismatch is logged as `DOC_HASH_MISMATCH` |
| 3 | PyMuPDF / python-docx / BeautifulSoup | PDF: repeated headers/footers and page numbers removed, hyphenation fixed. DOCX: Word list numbering rebuilt. HTML: nav/scripts stripped |
| 4 | `ClauseSplitter`: `4.2`, `Para 4.1`, `Rule 8`, `Section 3`, `(a)` sub-clauses, TOC lines dropped | Long clauses split at `(a)/(b)` with the parent lead-in kept |
| 5 | **Only clauses containing shall / must / mandatory / required / obligated to go to GPT-4o** | In the sample, 7 of 13 clauses are sent. Big cost saving on real CARs |
| 6 | Strict JSON schema output, then validation | Citation must be verbatim in the clause, otherwise it is replaced by the real sentence. Low confidence (< 0.5) dropped, duplicates removed |
| 6 | **Owner and severity come from the rule table, not GPT** | Same clause always gets the same result. Severity is evaluated on the cited sentence |
| 7 | text-embedding-3-small, one batched call, `embedding_cache` table | Agent 3 reuses these vectors: zero extra embedding cost |
| 8-9 | Old obligations for the document are replaced in one transaction, audit events written | CASCADE removes old mappings, new rows are PENDING, so Agent 3 re-maps |

Safety and idempotency
* Unchanged file + existing obligations → `SKIPPED_UNCHANGED` with no LLM calls (`force=true` to override).
* If more than 20% of clauses fail at the LLM, nothing is replaced and the previous obligations are kept.
* Documents with status `MISSING` or `HEALING` (Agent 1 self-heal in progress) return 409.
* Audit events: `EXTRACTION_STARTED`, `OBLIGATIONS_EXTRACTED` (with token usage), `OBLIGATIONS_REPROCESSED`, `EXTRACTION_FAILED`, `DOC_HASH_MISMATCH`.

## API (Agents 2 and 3; Agent 1 listed above)
| Method | Path | |
|---|---|---|
| POST | `/api/obligations/extract/{document_id}?force=false&run_in_background=false` | Agent 2 |
| GET | `/api/obligations/document/{document_id}` | Stored obligations |
| POST | `/api/mapping/ingest` | Agent 3: index enterprise repository |
| POST | `/api/mapping/map/pending`, `/map/document/{doc_code}`, `/map/obligations` | Agent 3: map |
| GET | `/api/mapping/impact/{doc_code}` | Policies / controls / systems per obligation |
| PATCH | `/api/mapping/mappings/{id}` | Compliance officer: CONFIRMED / REJECTED |

Errors: 400 source URL not allowed, 404 document or file not found, 409 document not ready (MISSING/HEALING),
422 unreadable file (e.g. scanned PDF without text), 502 regulator site or LLM failure, 503 LLM not configured.

### Sample request
```http
POST /api/obligations/extract/1
```

### Sample response (shortened)
```json
{
  "document_id": 1,
  "doc_code": "DGCA_CAR_API_Retention",
  "regulator": "DGCA",
  "status": "COMPLETED",
  "reprocessed": false,
  "file_sha256": "4c9402eff7533a6524e5a524c993a4f601485412b5e068ec0773360518dd7d54",
  "hash_matches_registry": true,
  "format": "pdf",
  "page_count": 3,
  "total_clauses": 13,
  "candidate_clauses": 7,
  "skipped_non_mandatory": 6,
  "failed_clauses": [],
  "obligations_extracted": 7,
  "dropped_low_confidence": 0,
  "duplicates_removed": 0,
  "citations_repaired": 1,
  "by_type": {"Data Retention": 1, "Record Keeping": 1, "Cyber Security": 1, "Access Control": 1,
              "Incident Management": 1, "Training Compliance": 1, "Data Privacy": 1},
  "by_severity": {"HIGH": 6, "MEDIUM": 1},
  "usage": {"model": "gpt-4o", "llm_calls": 7, "prompt_tokens": 6900, "completion_tokens": 1050,
            "embedding_model": "text-embedding-3-small", "embedding_tokens": 96, "embedding_cache_hits": 0},
  "duration_ms": 8400,
  "mapping_queued": true,
  "warnings": [],
  "obligations": [
    {
      "id": 2,
      "clause_ref": "4.2",
      "obligation_text": "The operator shall retain passenger API records for a minimum of 5 years from the date of travel.",
      "obligation_type": "Data Retention",
      "owner_function": "Data Governance",
      "severity": "HIGH",
      "citation": "Passenger API records shall be retained for a minimum period of 5 years from the date of travel",
      "confidence_score": 96.0,
      "target_system": "APIS",
      "mapping_status": "PENDING",
      "created_at": "2026-11-28T01:39:25.222474"
    }
  ]
}
```

### Agent 3 result for the same clause (`GET /api/mapping/impact/DGCA_CAR_API_Retention`)
```json
{
  "obligation_id": 2, "clause": "4.2", "severity": "HIGH", "mapping_status": "MAPPED",
  "policies": [{"code": "PASSENGER_DATA_POLICY#4.1", "name": "Passenger Data Policy", "link_type": "DIRECT",
                "relevance": 95.0,
                "current_provision": "4.1 Passenger API data shall be retained for a period of 3 years from the date of travel."}],
  "controls": [{"code": "CTRL-001", "name": "APIS Data Retention", "link_type": "SUPPORTING", "relevance": 95.0}],
  "systems":  [{"code": "APIS_SCHEDULER", "name": "APIS Scheduler", "link_type": "SUPPORTING", "relevance": 95.0}]
}
```
That "5 years vs 3 years" pair is exactly what the Gap Analysis Agent (4) needs.

## Agent 3 summary
Hybrid retrieval in SQL (pgvector + full-text + policy→control→system links) selects candidates at zero LLM cost.
gpt-4o-mini picks the impacted assets; gpt-4o is used only when confidence is low or severity is CRITICAL.
Invented ids are dropped and `current_provision` is kept only if it is verbatim. The CLI runs from `backend/`:
`python -m agents.policy_mapping ingest | map-pending | map-doc CODE | impact CODE`.

Enterprise repository layout (local folder or Blob): `policies/`, `sops/`, `audit_procedures/`, `security_standards/`,
`control_registers/{systems,controls}.json`. `_DRAFT` files are ignored. Only the highest approved version is indexed.

## Agent 4: Compliance Gap Assessment
`POST /api/gaps/analyze/{document_id}[?force=true&run_in_background=true]` and `GET /api/gaps/{document_id}[?risk_rating=&gap_type=]`.
Runs automatically after Agent 3 (`AUTO_ASSESS_AFTER_MAPPING`). Run `POST /api/mapping/ingest` first; with no controls registered it returns 409.

How an obligation is assessed
1. Reads Agent 3's mappings from `obligation_mappings` (the spec's `obligation_control_mappings`). REJECTED and CONTEXTUAL links are ignored.
2. Rules check the primary control from the register: failed test (Control Ineffective), no or stale evidence (Evidence Missing), manual operation (Manual Process Risk).
3. GPT-4o compares each parameter (number, period, deadline, scope) with the control and policy text, and quotes its evidence. Quotes not found in the source are flagged and cap confidence at 0.6.
4. Rules decide Missing Control (no control, or none applicable), cap coverage (unmet parameter 60, failed test 49), and compute risk and confidence.

Risk rules: no control = CRITICAL; coverage below 50 = HIGH; 50 to 80 = MEDIUM; above 80 = LOW. Two documented adjustments only ever raise a rating:
a shall/must (HIGH severity) obligation in the MEDIUM band becomes HIGH (this is how the spec's "65% = HIGH" example holds), and an evidence or effectiveness gap on a
mandatory obligation is at least MEDIUM. Turn the first off with `GAP_ESCALATE_HIGH_SEVERITY=false`.

One row per obligation (`UNIQUE(obligation_id)`). Compliant obligations are stored with `gap_type = "No Gap"` so coverage can be reported. Obligations Agent 3 has not
finished are listed in `pending_mapping`. Unchanged inputs are skipped through a fingerprint, so a re-run costs no tokens. `stale` marks rows whose obligation was re-mapped later.
Control register columns added for this agent: `automation_level` (AUTOMATED/HYBRID/MANUAL), `evidence_source`, `last_evidence_at`, `test_result` (PASSED/FAILED/NOT_TESTED).

## Agent 5: Regulatory Change Impact & Remediation
`POST /api/impact-analysis/{document_id}[?force=true&run_in_background=true&compare_to_document_id=N]`,
`GET /api/impact-analysis/{document_id}[?risk_rating=&change_type=]`, `GET /api/remediation-tasks/{document_id}[?status=&priority=&owner_team=]`.
Runs automatically after Agent 4 (`AUTO_IMPACT_AFTER_ASSESSMENT`). Regulators profiled for GPT-4o: DGCA, BCAS, CERT-IN, DPDP, ICAO, IATA (any other regulator still works, without a profile).

Where "previous regulation" comes from: Agent 2 replaces a document's obligations when a new file version is extracted. Just before it does, it now copies the old
obligations and the controls / systems they were mapped to into `regulation_obligation_versions` (last `OBLIGATION_VERSIONS_KEEP` versions). Agent 5 diffs the newest copy
against the current obligations. The first version of a document has nothing to compare, so every obligation counts as NEW_OBLIGATION (`IMPACT_FIRST_VERSION_AS_NEW=false` to skip).
`compare_to_document_id` compares against another document instead (for example a new circular that supersedes an old one).

How a change is analysed
1. Diff (rules): identical text is skipped; the rest is paired by wording and embedding similarity (and clause number) above `IMPACT_MATCH_THRESHOLD`; unpaired old = REMOVED, unpaired new = NEW.
   Changed numbers (years, days, hours, %), modal verbs (shall/must/may) and negations are extracted. Wording-only edits are marked minor.
2. Candidates (rules): controls and systems Agent 3 mapped to the new obligation (and to the old one), systems the controls run on, policy sections, owner teams, Agent 4's current gap.
3. GPT-4o: summary, which candidates truly have to change, extra business functions, 1 to 4 remediation tasks. It can only choose among candidates. If it fails, the change is still stored from rules alone with `needs_review=true`.
4. Risk (rules, `services/risk_service.py`): critical system impacted = CRITICAL; security requirement changed = HIGH; retention changed = HIGH (the spec's own sample);
   reporting changed = MEDIUM; minor = LOW. New obligation MEDIUM (HIGH for retention or security), severity raised MEDIUM, removed or severity lowered LOW.
   Raised only by an existing HIGH/CRITICAL Agent 4 gap or a change no control covers (at least HIGH). Overall rating = highest individual rating; overall score (0-100) rises within it with the number of changes.
5. Tasks (rules + GPT-4o): priority = the impact's rating, due days 15 / 30 / 60 / 90 for CRITICAL / HIGH / MEDIUM / LOW (re-test +30). Re-running keeps IN_PROGRESS and DONE tasks.

"Critical system" needs a criticality per system: add `"criticality": "CRITICAL|HIGH|MEDIUM|LOW"` to `control_registers/systems.json` and run `POST /api/mapping/ingest`.
Unchanged changes are skipped by fingerprint, so re-runs cost no tokens. Changes whose new obligation Agent 3 has not mapped yet are listed in `pending_mapping` and analysed on the next run.

### Sample request
```bash
curl -X POST "localhost:8000/api/impact-analysis/12"
curl "localhost:8000/api/impact-analysis/12?risk_rating=HIGH"
curl "localhost:8000/api/remediation-tasks/12?status=OPEN&owner_team=Data%20Governance"
```

### Sample response (shortened; one change)
```json
{
  "document_id": 12, "doc_code": "DGCA_CAR_API_Retention", "regulator": "DGCA", "status": "COMPLETED",
  "baseline": "previous version of this document (replaced by v2.0)", "previous_version": "v1.0", "current_version": "v2.0",
  "overall_risk_rating": "HIGH", "overall_risk_score": 72.5,
  "summary": "1 change(s) vs previous version of this document (replaced by v2.0): 1 HIGH. Overall risk HIGH (72.5). Affects 1 control(s), 2 system(s) and 1 team(s); 4 open remediation task(s). Highest risk: RETENTION_CHANGE at clause 4.2 (The minimum retention period for API records rises from 3 years to 5 years.).",
  "analyzed": 1, "unchanged": 0, "rules_only": 0, "pending_mapping": [],
  "stats": {"total": 1, "by_change_type": {"RETENTION_CHANGE": 1}, "by_risk": {"HIGH": 1}, "needs_review": 0, "tasks_total": 4, "tasks_open": 4},
  "usage": {"model": "gpt-4o", "llm_calls": 1, "prompt_tokens": 910, "completion_tokens": 240},
  "impacts": [{
    "id": 31, "document_id": 12,
    "change_type": "RETENTION_CHANGE",
    "old_clause": "Operators shall retain API records for a minimum of 3 years.",
    "new_clause": "Operators shall retain API records for a minimum of 5 years.",
    "affected_control": "APIS Data Retention",
    "affected_system": "Data Warehouse",
    "affected_team": "Data Governance",
    "risk_rating": "HIGH",
    "remediation_action": "Update retention configuration to 5 years",
    "confidence_score": 0.92,
    "clause_ref": "4.2", "risk_score": 72.5, "needs_review": false,
    "summary": "The minimum retention period for API records rises from 3 years to 5 years.",
    "affected_controls": [{"code": "CTRL-001", "name": "APIS Data Retention", "owner": "Data Governance"}],
    "affected_systems": [{"code": "DATA_WAREHOUSE", "name": "Data Warehouse", "criticality": "HIGH", "owner": "Data Governance"},
                         {"code": "APIS_SCHEDULER", "name": "APIS Scheduler", "criticality": "HIGH", "owner": "IT - Passenger Systems"}],
    "affected_teams": ["Data Governance", "IT - Passenger Systems"],
    "tasks": [
      {"id": 71, "impact_id": 31, "task_name": "Update retention configuration to 5 years", "owner_team": "Data Governance", "priority": "HIGH", "due_days": 30, "status": "OPEN"},
      {"id": 72, "impact_id": 31, "task_name": "Reconfigure and validate Data Warehouse against the revised requirement (3 years -> 5 years)", "owner_team": "Data Governance", "priority": "HIGH", "due_days": 30, "status": "OPEN"},
      {"id": 73, "impact_id": 31, "task_name": "Revise Passenger Data Policy section 4 to reflect the revised requirement (3 years -> 5 years)", "owner_team": "Data Governance", "priority": "HIGH", "due_days": 30, "status": "OPEN"},
      {"id": 74, "impact_id": 31, "task_name": "Re-test APIS Data Retention and retain evidence of compliance", "owner_team": "Data Governance", "priority": "HIGH", "due_days": 60, "status": "OPEN"}
    ]
  }]
}
```
Errors: 404 `document_not_found`, 409 `document_not_ready`, 422 `invalid_comparison`, 503 `llm_not_configured`.

## Tests
```bash
pytest -q tests                                   # unit tests (no DB, no OpenAI)
TEST_DATABASE_URL=postgresql://... pytest -q tests  # + Agent 1→2→3→4 through the API: fake regulator site,
                                                    #   temp-folder blob, fake OpenAI (wipes that DB)
```
