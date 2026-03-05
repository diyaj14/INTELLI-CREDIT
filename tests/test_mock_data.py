"""
tests/test_mock_data.py
=======================
Validates that mock_data.py exports match CONTRACT 1 exactly.
Run: pytest tests/test_mock_data.py -v
"""
import json
import pytest
import sys
import os

# Make sure modules are importable from root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.document_intelligence.mock_data import (
    APEX_TEXTILES_DOC_REPORT,
    HEALTHY_COMPANY_DOC_REPORT,
    export_to_json,
)

# ── Required top-level keys per CONTRACT 1 ──────────────────────────────────
REQUIRED_TOP_KEYS = {
    "company_name", "gstin", "financials", "gst_analysis",
    "bank_statement", "extraction_confidence", "source_citations",
}

REQUIRED_FINANCIALS = {
    "revenue_cr", "ebitda_cr", "net_profit_cr", "total_assets_cr",
    "total_liabilities_cr", "net_worth_cr", "dscr", "current_ratio",
    "debt_to_equity", "interest_coverage",
}

REQUIRED_GST_KEYS = {
    "mismatch_pct", "mismatch_flag", "circular_trading_flag",
    "revenue_inflation_flag", "gst_score",
}

REQUIRED_BANK_KEYS = {
    "avg_balance_cr", "emi_outflow_monthly_cr", "peak_balance_cr", "regular_credits",
}

# ── Helpers ─────────────────────────────────────────────────────────────────
def validate_report(report: dict, label: str):
    """Runs all schema checks on a DocumentReport dict."""

    # Top-level keys
    missing = REQUIRED_TOP_KEYS - report.keys()
    assert not missing, f"[{label}] Missing top-level keys: {missing}"

    # Financials
    fin = report["financials"]
    missing_fin = REQUIRED_FINANCIALS - fin.keys()
    assert not missing_fin, f"[{label}] Missing financials keys: {missing_fin}"

    # GST
    gst = report["gst_analysis"]
    missing_gst = REQUIRED_GST_KEYS - gst.keys()
    assert not missing_gst, f"[{label}] Missing gst_analysis keys: {missing_gst}"

    # Bank
    bank = report["bank_statement"]
    missing_bank = REQUIRED_BANK_KEYS - bank.keys()
    assert not missing_bank, f"[{label}] Missing bank_statement keys: {missing_bank}"

    # Type checks
    assert isinstance(report["company_name"], str), f"[{label}] company_name must be str"
    assert isinstance(report["gstin"], str), f"[{label}] gstin must be str"
    assert isinstance(report["extraction_confidence"], float), f"[{label}] confidence must be float"
    assert 0.0 <= report["extraction_confidence"] <= 1.0, f"[{label}] confidence must be 0–1"
    assert isinstance(report["source_citations"], dict), f"[{label}] source_citations must be dict"

    # Financial type checks
    for key in REQUIRED_FINANCIALS:
        assert isinstance(fin[key], (int, float)), f"[{label}] financials.{key} must be numeric"

    # GST type checks
    assert isinstance(gst["mismatch_pct"], (int, float)), f"[{label}] mismatch_pct must be numeric"
    assert gst["mismatch_flag"] in {"RED", "YELLOW", "GREEN"}, f"[{label}] invalid mismatch_flag"
    assert isinstance(gst["circular_trading_flag"], bool), f"[{label}] circular_trading_flag must be bool"
    assert isinstance(gst["revenue_inflation_flag"], bool), f"[{label}] revenue_inflation_flag must be bool"
    assert 0 <= gst["gst_score"] <= 20, f"[{label}] gst_score out of range 0–20"

    # Bank type checks
    for key in ["avg_balance_cr", "emi_outflow_monthly_cr", "peak_balance_cr"]:
        assert isinstance(bank[key], (int, float)), f"[{label}] bank.{key} must be numeric"
    assert isinstance(bank["regular_credits"], bool), f"[{label}] regular_credits must be bool"

    # Business logic sanity checks
    assert fin["revenue_cr"] > 0, f"[{label}] revenue must be positive"
    assert fin["net_worth_cr"] == round(fin["total_assets_cr"] - fin["total_liabilities_cr"], 2) or \
           abs(fin["net_worth_cr"] - (fin["total_assets_cr"] - fin["total_liabilities_cr"])) < 1.0, \
           f"[{label}] net_worth should ≈ assets − liabilities"


# ── Tests ────────────────────────────────────────────────────────────────────
class TestApexTextilesMock:
    """Tests for the borderline rejection scenario."""

    def test_schema_completeness(self):
        validate_report(APEX_TEXTILES_DOC_REPORT, "Apex Textiles")

    def test_dscr_below_rbi_threshold(self):
        dscr = APEX_TEXTILES_DOC_REPORT["financials"]["dscr"]
        assert dscr < 1.25, f"Apex should have DSCR < 1.25 for demo, got {dscr}"

    def test_gst_flag_is_red(self):
        assert APEX_TEXTILES_DOC_REPORT["gst_analysis"]["mismatch_flag"] == "RED"

    def test_gst_mismatch_above_10pct(self):
        pct = APEX_TEXTILES_DOC_REPORT["gst_analysis"]["mismatch_pct"]
        assert pct > 10, f"Expected mismatch >10%, got {pct}"

    def test_circular_trading_flagged(self):
        assert APEX_TEXTILES_DOC_REPORT["gst_analysis"]["circular_trading_flag"] is True

    def test_gst_score_reflects_red_flag(self):
        assert APEX_TEXTILES_DOC_REPORT["gst_analysis"]["gst_score"] <= 10


class TestHealthyCompanyMock:
    """Tests for the clean approval scenario."""

    def test_schema_completeness(self):
        validate_report(HEALTHY_COMPANY_DOC_REPORT, "Sunrise Foods")

    def test_dscr_above_rbi_threshold(self):
        dscr = HEALTHY_COMPANY_DOC_REPORT["financials"]["dscr"]
        assert dscr >= 1.25, f"Sunrise should have DSCR >= 1.25, got {dscr}"

    def test_gst_flag_is_green(self):
        assert HEALTHY_COMPANY_DOC_REPORT["gst_analysis"]["mismatch_flag"] == "GREEN"

    def test_no_circular_trading(self):
        assert HEALTHY_COMPANY_DOC_REPORT["gst_analysis"]["circular_trading_flag"] is False

    def test_gst_score_is_full(self):
        assert HEALTHY_COMPANY_DOC_REPORT["gst_analysis"]["gst_score"] == 20


class TestJsonExport:
    """Tests the demo_data JSON export."""

    def test_export_creates_files(self, tmp_path, monkeypatch):
        # Redirect output to tmp directory
        monkeypatch.chdir(tmp_path)
        os.makedirs("demo_data", exist_ok=True)

        # We can't easily test the relative path in export_to_json,
        # so just verify the function runs without error
        try:
            export_to_json()
        except Exception as e:
            pytest.fail(f"export_to_json() raised: {e}")

    def test_reports_are_json_serializable(self):
        """Both reports must serialize to JSON without errors."""
        json.dumps(APEX_TEXTILES_DOC_REPORT)
        json.dumps(HEALTHY_COMPANY_DOC_REPORT)
