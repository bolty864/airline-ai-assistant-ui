"""Agent 4 against a real Postgres: seeded obligations, mappings and controls, GPT-4o replaced by FakeOpenAI.

Needs Postgres + pgvector:  TEST_DATABASE_URL=postgresql://... pytest -q tests   (wipes that DB)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import psycopg
import pytest

from tests.conftest import FakeOpenAI

BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


def _sql(query: str, *args):
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        cur = conn.execute(query, args)
        return cur.fetchall() if cur.description else []


def _seed() -> dict[str, int]:
    """One document, six obligations, four controls. Returns ids by label."""
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for f in ("001_base_schema.sql", "002_agent3_policy_control_mapping.sql", "003_agent4_gap_assessment.sql", "004_agent5_impact_assessment.sql"):
            conn.execute((BACKEND / "sql" / f).read_text())
        one = lambda q, *a: conn.execute(q, a).fetchone()[0]       # noqa: E731
        doc = one("""INSERT INTO regulatory_documents (doc_code, filename, regulator, title, source_url, blob_path, sha256_hash)
                     VALUES ('DOC1','d.pdf','DGCA','Test CAR','http://x','d.pdf','h') RETURNING id""")
        ids = {"doc": doc}

        def control(code, name, desc, ctype, owner, freq, auto, evidence, test):
            return one("""INSERT INTO controls (control_code,name,description,control_type,owner_function,frequency,
                          automation_level,evidence_source,test_result) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       code, name, desc, ctype, owner, freq, auto, evidence, test)

        ids["A"] = control("CTRL-A", "Retention purge", "Purge job deletes records after 3 years elapsed. Retention period configured.",
                           "Preventive", "Data Governance", "Monthly", "AUTOMATED", "Purge job report", "PASSED")
        ids["B"] = control("CTRL-B", "Access review", "Manager performs quarterly access review of privileged accounts.",
                           "Detective", "Information Security", "Quarterly", "MANUAL", None, "NOT_TESTED")
        ids["C"] = control("CTRL-C", "Encryption", "Passenger data is encrypted at rest and in transit using AES-256.",
                           "Preventive", "Information Security", "Continuous", "AUTOMATED", "Key Vault logs", "PASSED")
        ids["D"] = control("CTRL-D", "Extended retention", "Records retained for 7 years in cold storage.",
                           "Preventive", "Data Governance", "Annual", "AUTOMATED", "Report", "PASSED")
        edoc = one("""INSERT INTO enterprise_documents (doc_code,doc_type,title,filename,blob_path,sha256_hash)
                      VALUES ('PASSENGER_POLICY','POLICY','Passenger Policy','p.md','p.md','h') RETURNING id""")
        ids["chunk"] = one("""INSERT INTO enterprise_chunks (document_id,chunk_index,section_ref,heading,content,content_hash)
                              VALUES (%s,0,'4','Retention','Passenger records are retained for 3 years.','c') RETURNING id""", edoc)

        def ob(label, text, status, severity="HIGH"):
            ids[label] = one("""INSERT INTO compliance_obligations (document_id,clause_ref,obligation_text,severity,obligation_type,
                                owner_function,confidence_score,mapping_status,mapped_at)
                                VALUES (%s,%s,%s,%s,'Other','Compliance',95,%s,NOW()) RETURNING id""",
                               doc, label, text, severity, status)

        ob("O1", "Operators shall retain passenger records for at least 5 years.", "MAPPED")
        ob("O2", "Operators shall encrypt passenger data at rest and in transit.", "MAPPED")
        ob("O3", "Operators shall perform access review of privileged accounts every quarter.", "MAPPED")
        ob("O4", "Operators shall notify the authority within 6 hours of any breach.", "UNMAPPED")
        ob("O5", "Operators shall keep flight logs.", "PENDING")
        ob("O6", "Operators shall conduct pilot simulator training annually.", "NEEDS_REVIEW")

        def mapping(o, ttype, tid, code, link, rel, review="PROPOSED", provision=None):
            conn.execute("""INSERT INTO obligation_mappings (obligation_id,target_type,target_id,target_code,link_type,
                            relevance_score,review_status,current_provision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (ids[o], ttype, tid, code, link, rel, review, provision))

        mapping("O1", "CONTROL", ids["A"], "CTRL-A", "DIRECT", 90)
        mapping("O1", "POLICY_SECTION", ids["chunk"], "PASSENGER_POLICY#4", "DIRECT", 85,
                provision="Passenger records are retained for 3 years.")
        mapping("O1", "CONTROL", ids["D"], "CTRL-D", "DIRECT", 95, review="REJECTED")      # must be ignored
        mapping("O2", "CONTROL", ids["C"], "CTRL-C", "DIRECT", 92)
        mapping("O3", "CONTROL", ids["B"], "CTRL-B", "DIRECT", 88)
        mapping("O6", "CONTROL", ids["C"], "CTRL-C", "SUPPORTING", 60)
        return ids


def test_gap_assessment_scenarios():
    ids = _seed()
    asyncio.run(_run(ids))


async def _run(ids: dict[str, int]):
    import providers
    from agents.pipeline import get_pipeline
    from main import app

    fake = FakeOpenAI()
    providers.override(llm_client=fake)
    doc = ids["doc"]
    gap_calls = lambda: sum(1 for s, _ in fake.calls if s == "gap_assessment")     # noqa: E731

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
        # ---------------------------------------------------------------- first run
        r = await c.post(f"/api/gaps/analyze/{doc}")
        assert r.status_code == 200, r.text
        res = r.json()
        by = {a["obligation_id"]: a for a in res["assessments"]}
        assert res["status"] == "PARTIAL" and res["assessed"] == 5 and res["llm_assessed"] == 4
        assert res["pending_mapping"] == [ids["O5"]] and ids["O5"] not in by
        assert gap_calls() == 4                                    # O4 has no controls: decided by rules, no LLM call

        o1 = by[ids["O1"]]       # 3 vs 5 years: partial, mandatory obligation, 55% -> MEDIUM band -> escalated to HIGH
        assert o1["gap_type"] == "Partial Coverage" and o1["coverage_score"] == 55 and o1["risk_rating"] == "HIGH"
        assert "CTRL-A" in o1["observation"] and o1["mapping_id"] is not None and not o1["needs_review"]
        assert "30 days" in o1["recommendation"] and o1["confidence_score"] == 0.9
        assert o1["details"]["primary_control"] == "CTRL-A"        # the REJECTED CTRL-D mapping was not used

        o2 = by[ids["O2"]]
        assert o2["gap_type"] == "No Gap" and o2["risk_rating"] == "LOW" and o2["coverage_score"] == 92

        o3 = by[ids["O3"]]       # control is good on paper but has no evidence and is manual
        assert o3["gap_type"] == "Evidence Missing" and o3["additional_gaps"] == ["Manual Process Risk"]
        assert o3["risk_rating"] == "MEDIUM"                       # floor for evidence gaps on mandatory obligations

        o4 = by[ids["O4"]]       # Agent 3 found nothing
        assert (o4["gap_type"], o4["risk_rating"], o4["coverage_score"]) == ("Missing Control", "CRITICAL", 0)
        assert o4["needs_review"] and o4["confidence_score"] == 0.9 and "Compliance" in o4["recommendation"]

        o6 = by[ids["O6"]]       # a control was mapped but it does not do what is required
        assert o6["gap_type"] == "Missing Control" and o6["risk_rating"] == "CRITICAL" and o6["needs_review"]

        s = res["stats"]
        assert s["total"] == 5 and s["compliant"] == 1 and s["with_gaps"] == 4
        assert s["by_risk"] == {"HIGH": 1, "LOW": 1, "MEDIUM": 1, "CRITICAL": 2} and s["needs_review"] == 2
        assert [a["risk_rating"] for a in res["assessments"]][:2] == ["CRITICAL", "CRITICAL"]   # highest risk first
        assert len(_sql("SELECT 1 FROM compliance_gap_assessments")) == 5

        # ---------------------------------------------------------------- unchanged inputs: no LLM, no writes
        res = (await c.post(f"/api/gaps/analyze/{doc}")).json()
        assert res["assessed"] == 0 and res["unchanged"] == 5 and gap_calls() == 4

        # ---------------------------------------------------------------- control fails its test -> only dependants re-run
        _sql("UPDATE controls SET test_result = 'FAILED' WHERE control_code = 'CTRL-C'")
        res = (await c.post(f"/api/gaps/analyze/{doc}")).json()
        assert res["assessed"] == 2 and res["unchanged"] == 3     # O2 and O6 use CTRL-C
        o2 = {a["obligation_id"]: a for a in res["assessments"]}[ids["O2"]]
        assert o2["gap_type"] == "Control Ineffective" and o2["coverage_score"] == 49 and o2["risk_rating"] == "HIGH"
        assert len(_sql("SELECT 1 FROM compliance_gap_assessments")) == 5      # updated in place, not duplicated

        # ---------------------------------------------------------------- Agent 3 re-maps an obligation -> flagged stale
        _sql("UPDATE compliance_obligations SET mapped_at = NOW() + interval '1 minute' WHERE id = %s", ids["O1"])
        rep = (await c.get(f"/api/gaps/{doc}")).json()
        assert {a["obligation_id"] for a in rep["assessments"] if a["stale"]} == {ids["O1"]} and rep["stats"]["stale"] == 1

        # ---------------------------------------------------------------- filters, errors, background mode
        crit = (await c.get(f"/api/gaps/{doc}", params={"risk_rating": "CRITICAL"})).json()
        assert {a["obligation_id"] for a in crit["assessments"]} == {ids["O4"], ids["O6"]}
        only = (await c.get(f"/api/gaps/{doc}", params={"gap_type": "Evidence Missing"})).json()
        assert [a["obligation_id"] for a in only["assessments"]] == [ids["O3"]]
        assert (await c.get(f"/api/gaps/{doc}", params={"risk_rating": "SEVERE"})).status_code == 422
        assert (await c.get("/api/gaps/9999")).status_code == 404
        assert (await c.post("/api/gaps/analyze/9999")).status_code == 404

        r = await c.post(f"/api/gaps/analyze/{doc}", params={"run_in_background": "true", "force": "true"})
        assert r.status_code == 202
        await get_pipeline().drain()
        assert gap_calls() > 6                                    # force re-assessed everything that is mapped

        # ---------------------------------------------------------------- Agent 3 repository never indexed
        _sql("DELETE FROM controls")
        r = await c.post(f"/api/gaps/analyze/{doc}")
        assert r.status_code == 409 and r.json()["error"] == "enterprise_repository_empty"
