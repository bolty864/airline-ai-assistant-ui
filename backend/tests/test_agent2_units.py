from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document

from agents.obligation_extraction_agent import ObligationExtractionAgent
from services.clause_splitter import ClauseSplitter
from services.document_types import DocumentParseError
from services.llm_extractor import ExtractedObligation
from services.obligation_rules import has_mandatory_language, normalize_type, owner_for, severity_for
from services.parser_factory import ParserFactory

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data/demo_sources"
EXPECTED_CANDIDATES = ["4.1", "4.2", "4.3", "5.1", "5.2", "6.1", "7.1"]


@pytest.mark.parametrize("name", ["DGCA_CAR_API_Retention.pdf", "DGCA_CAR_API_Retention.html"])
def test_parse_and_split_sample(name):
    parsed = ParserFactory().parse(name, (SAMPLE / name).read_bytes())
    clauses = ClauseSplitter().split(parsed.text)
    assert [c.clause_number for c in clauses if c.is_candidate] == EXPECTED_CANDIDATES
    four_two = next(c for c in clauses if c.clause_number == "4.2")
    assert four_two.heading == "DATA RETENTION" and "5 years" in four_two.text
    assert "SAMPLE - NOT AN OFFICIAL" not in parsed.text  # repeating page header removed (pdf) / absent (html)
    assert "Home | Circulars" not in parsed.text          # nav stripped (html)


def test_docx_rebuilds_list_numbers():
    doc = Document()
    doc.add_heading("Retention", level=1)
    doc.add_paragraph("Passenger records shall be retained for 5 years.", style="List Number")
    doc.add_paragraph("Logs must be kept for 90 days.", style="List Number")
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Record", "Period"
    buf = io.BytesIO()
    doc.save(buf)
    parsed = ParserFactory().parse("x.docx", buf.getvalue())
    assert "1. Passenger records shall" in parsed.text and "2. Logs must" in parsed.text
    assert "Record | Period" in parsed.text


def test_parser_errors():
    with pytest.raises(DocumentParseError):
        ParserFactory().parse("x.pdf", b"%PDF-1.4 broken")
    with pytest.raises(DocumentParseError):
        ParserFactory().parse("x.xyz", b"hello")


def test_splitter_variants():
    text = "\n".join([
        "Contents",
        "4.2 Data retention ........ 12",          # TOC line, ignored
        "Rule 8. The operator shall notify the Board within 72 hours.",
        "Section 9 Grievances",
        "Para 9.1 A grievance officer must be appointed.",
        "It lasts 1.5 hours before departure.",   # not a clause start (lowercase)
    ])
    clauses = ClauseSplitter().split(text)
    nums = [c.clause_number for c in clauses]
    assert nums == ["PREAMBLE", "8", "9.1"]
    assert clauses[2].heading == "Grievances"


def test_long_clause_split_into_subclauses():
    sub = " ".join(["word"] * 120)
    text = "5.1 The operator shall ensure the following:\n" + "\n".join(f"({c}) {sub} shall apply." for c in "abc")
    clauses = ClauseSplitter(max_clause_chars=800).split(text)
    assert [c.clause_number for c in clauses] == ["5.1", "5.1(a)", "5.1(b)", "5.1(c)"]
    assert all(c.text.startswith("5.1 The operator shall ensure") for c in clauses[1:])


def test_no_numbering_falls_back_to_paragraphs():
    clauses = ClauseSplitter().split("Data fiduciaries shall obtain consent.\n\nThis is background.")
    assert clauses[0].clause_number == "Para-1"


def test_rules():
    assert severity_for("Records shall be kept") == "HIGH"
    assert severity_for("Operators must encrypt") == "HIGH"
    assert severity_for("Operators are required to review") == "MEDIUM"
    assert severity_for("Training is mandatory") == "LOW"   # per the spec's rule table
    assert owner_for("Consent Management") == "Privacy Office"
    assert owner_for("Other") == "Compliance Office"
    assert normalize_type("data retention") == "Data Retention" and normalize_type("Weird") == "Other"
    assert has_mandatory_language("is obligated to") and not has_mandatory_language("requirements apply")


def test_citation_repair():
    clause = "4.1 Operators shall transmit API data to the authority before departure. Other text here."
    ob = ExtractedObligation("4.1", "The operator shall transmit API data before departure.", "Other", "", "HIGH",
                             "Operators must send API data", 0.9)
    citation, repaired = ObligationExtractionAgent._verified_citation(ob, clause)
    assert repaired and citation.startswith("4.1 Operators shall transmit API data")
    ob.citation = "Operators shall transmit API data to the authority"
    assert ObligationExtractionAgent._verified_citation(ob, clause) == (ob.citation, False)
