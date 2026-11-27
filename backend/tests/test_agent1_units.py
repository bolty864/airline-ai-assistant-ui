from __future__ import annotations

from agents.regulatory_monitoring_agent import RegulatoryMonitoringAgent, bump_version
from services.parser_factory import ParserFactory
from services.scrapers import sanitize_doc_code


def test_doc_code_is_unique_per_url():
    a = sanitize_doc_code("DGCA", "View", "https://dgca.gov.in/a.pdf")
    b = sanitize_doc_code("DGCA", "View", "https://dgca.gov.in/b.pdf")
    assert a != b and a.startswith("DGCA_View_") and a == sanitize_doc_code("DGCA", "View", "https://dgca.gov.in/a.pdf")


def test_bump_version():
    assert bump_version("v1.0") == "v1.1" and bump_version("v2.9") == "v2.10" and bump_version(None) == "v1.1"


def test_format_from_content_not_extension():
    assert ParserFactory.detect_format("car.pdf", b"<!DOCTYPE html><html>error</html>") == "html"
    assert RegulatoryMonitoringAgent._filename("CAR 3/IV.pdf", "html") == "IV.html"
    assert RegulatoryMonitoringAgent._filename("DGCA CAR v2.pdf", "pdf") == "DGCA_CAR_v2.pdf"
