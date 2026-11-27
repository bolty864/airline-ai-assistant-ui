"""Agent 4 unit tests: risk rules, control quality, validation. No DB, no LLM."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from services.control_quality import check_control, stale_after_days
from services.gap_analyzer import GapAnalyzer, Prepared, select_assets
from services.gap_types import AssetView, GapType, ObligationView
from services.risk_scoring_service import coverage_band, score_risk

NOW = datetime(2026, 11, 28)


def control(**kw) -> AssetView:
    base = dict(mapping_id=1, target_type="CONTROL", code="CTRL-X", name="X", evidence_source="report",
                automation_level="AUTOMATED", control_type="Preventive", frequency="Monthly", test_result="PASSED",
                description="Purges after 3 years.", relevance=90.0)
    return AssetView(**{**base, **kw})


# ------------------------------------------------------------------ rating rules from the spec
def test_coverage_bands():
    assert coverage_band(49.9) == "HIGH"
    assert coverage_band(50) == "MEDIUM" and coverage_band(80) == "MEDIUM"
    assert coverage_band(80.1) == "LOW"


def test_no_control_is_critical():
    r = score_risk(0, "LOW", [GapType.MISSING_CONTROL], has_control=False)
    assert r.rating == "CRITICAL" and r.score >= 90


def test_high_severity_medium_band_escalates_to_high():
    assert score_risk(65, "HIGH", [GapType.PARTIAL_COVERAGE], True).rating == "HIGH"       # spec sample: 65 -> HIGH
    assert score_risk(65, "MEDIUM", [GapType.PARTIAL_COVERAGE], True).rating == "MEDIUM"
    assert score_risk(65, "HIGH", [GapType.PARTIAL_COVERAGE], True, escalate_high_severity=False).rating == "MEDIUM"


def test_evidence_gap_on_mandatory_obligation_floors_at_medium():
    assert score_risk(95, "HIGH", [GapType.EVIDENCE_MISSING], True).rating == "MEDIUM"
    assert score_risk(95, "LOW", [GapType.EVIDENCE_MISSING], True).rating == "LOW"


def test_score_stays_inside_rating_band_and_orders_by_coverage():
    worse, better = score_risk(20, "LOW", ["Partial Coverage"], True), score_risk(45, "LOW", ["Partial Coverage"], True)
    assert worse.rating == better.rating == "HIGH" and worse.score > better.score
    assert 65 <= better.score <= 89.99


# ------------------------------------------------------------------ control quality
def test_quality_flags():
    assert check_control(control(), NOW) == []
    assert [f.gap_type for f in check_control(control(test_result="FAILED"), NOW)] == [GapType.CONTROL_INEFFECTIVE]
    assert [f.gap_type for f in check_control(control(evidence_source=None), NOW)] == [GapType.EVIDENCE_MISSING]
    assert check_control(control(evidence_source=None), NOW, require_evidence=False) == []
    assert [f.gap_type for f in check_control(control(automation_level="MANUAL"), NOW)] == [GapType.MANUAL_PROCESS_RISK]
    assert check_control(control(automation_level="MANUAL", control_type="Governance"), NOW) == []


def test_stale_evidence_depends_on_frequency():
    assert stale_after_days("Monthly") == 45 and stale_after_days(None) == 400
    old = NOW - timedelta(days=60)
    assert check_control(control(last_evidence_at=old, frequency="Monthly"), NOW)[0].gap_type == GapType.EVIDENCE_MISSING
    assert check_control(control(last_evidence_at=old, frequency="Quarterly"), NOW) == []


# ------------------------------------------------------------------ asset selection and validation
def test_select_assets_caps_and_keys():
    assets = [control(mapping_id=i, code=f"C{i}", relevance=i) for i in range(1, 8)]
    chosen = select_assets(assets)
    assert [a.key for a in chosen] == ["C1", "C2", "C3", "C4"]
    assert chosen[0].relevance == 7                      # best relevance first


def test_validate_flags_invented_quotes():
    c = control(key="C1", description="Purges after 3 years.")
    prep = Prepared(ObligationView(id=1, text="t", regulator="r", document_title="d"), [c], {}, "fp")
    raw = {"applicable_control_found": True, "coverage": 50, "gap_types": ["Partial Coverage", "Evidence Missing"],
           "primary_ref": "C1", "supporting_refs": ["C1", "Z9"], "observation": "o", "recommendation": "r",
           "confidence": 0.9, "parameters": [
               {"parameter": "a", "required": "5", "actual": "3 years", "met": False, "source_ref": "C1",
                "actual_quote": "Purges after 3 years."},
               {"parameter": "b", "required": "x", "actual": "y", "met": True, "source_ref": "C1",
                "actual_quote": "never written anywhere"}]}
    out = GapAnalyzer.validate(raw, prep)
    assert [p.verified for p in out.parameters] == [True, False]
    assert out.gap_types == ["Partial Coverage"]         # the model may not report Evidence Missing itself
    assert out.supporting_refs == ["C1"] and out.warnings


def test_fingerprint_changes_with_control_state():
    analyzer = GapAnalyzer(SimpleNamespace(), SimpleNamespace(
        azure_openai_deployment="gpt-4o", gap_param_mismatch_cap=60, gap_failed_test_cap=49,
        gap_escalate_high_severity=True, gap_require_evidence=True, gap_review_confidence=0.7))
    ob = ObligationView(id=1, text="Retain 5 years", regulator="DGCA", document_title="CAR")
    a = analyzer.prepare(ob, [control()], NOW).fingerprint
    assert a == analyzer.prepare(ob, [control()], NOW).fingerprint
    assert a != analyzer.prepare(ob, [control(test_result="FAILED")], NOW).fingerprint
    assert a != analyzer.prepare(ob, [control(description="Purges after 5 years.")], NOW).fingerprint
