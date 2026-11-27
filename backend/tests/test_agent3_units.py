"""Agent 3 unit tests (no DB, no LLM)."""
from __future__ import annotations

from pathlib import Path


from agents.policy_mapping.documents import chunk_document, parse_filename, select_publishable
from agents.policy_mapping.retriever import build_tsquery, rrf_fuse

ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------- unit tests

def test_filename_versioning_skips_drafts():
    picked = select_publishable([
        "policies/Passenger_Data_Policy_v1_APPROVED.md",
        "policies/Passenger_Data_Policy_v2_DRAFT.md",
        "policies/Cyber_Security_Policy_v1.2_APPROVED.md",
        "policies/Cyber_Security_Policy_v1.10_APPROVED.md",
        "sops/APIS_Purge_SOP.docx",
        "policies/readme.png",
        "regulations/DGCA_CAR.pdf",   # not an enterprise folder: ignored
    ])
    by = {p.doc_code: p for p in picked}
    assert by["PASSENGER_DATA_POLICY"].version_tag == "v1.0"
    assert by["CYBER_SECURITY_POLICY"].version_tag == "v1.10"
    assert by["APIS_PURGE_SOP"].doc_type == "SOP"
    assert len(picked) == 3


def test_chunker_keeps_clause_refs():
    text = (ROOT / "sample_data/enterprise/policies/Passenger_Data_Policy_v1_APPROVED.md").read_text()
    title, chunks = chunk_document(text.splitlines())
    assert title == "Passenger Data Policy"
    retention = [c for c in chunks if "Retention" in c.heading][0]
    assert retention.section_ref in {"4", "4.1"}
    assert "3 years" in retention.content


def test_long_section_is_split():
    lines = ["# Big", "## 1. Huge"] + [("word " * 100).strip(), ""] * 10
    _, chunks = chunk_document(lines, max_words=320)
    assert len(chunks) >= 3 and all(len(c.content.split()) <= 320 for c in chunks)


def test_tsquery_and_rrf():
    q = build_tsquery("Passenger API records shall be retained for 5 years")
    assert "shall" not in q and "api" in q and "retained" in q
    fused = rrf_fuse([1, 2, 3], [3, 4])
    assert max(fused, key=fused.get) == 3
