"""
test_demo_mode.py — Tests for Feature 4: Demo Mode Flag
=========================================================
Tests that run_pipeline(demo_mode=True) returns the cached Apex Textiles
demo scenario instantly without touching any real files.
"""

import pytest
from modules.document_intelligence.document_pipeline import run_pipeline
from modules.document_intelligence.mock_data import APEX_TEXTILES_DOC_REPORT


# ──────────────────────────────────────────────────────────────────────────────
# Demo Mode Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDemoMode:

    def test_demo_mode_returns_dict(self):
        """run_pipeline(demo_mode=True) should return a dict."""
        result = run_pipeline([], demo_mode=True)
        assert isinstance(result, dict)

    def test_demo_mode_skips_file_parsing(self):
        """Demo mode must work even with empty file list (no real files needed)."""
        result = run_pipeline([], demo_mode=True)
        assert result is not None

    def test_demo_mode_has_all_contract1_keys(self):
        """All CONTRACT 1 required keys must be present in demo output."""
        required_keys = {
            "company_name", "gstin", "financials", "gst_analysis",
            "bank_statement", "extraction_confidence", "source_citations",
            "source_citations_structured", "early_warning_signals",
            "multi_year_financials", "yoy_changes", "trend_signals",
        }
        result = run_pipeline([], demo_mode=True)
        missing = required_keys - set(result.keys())
        assert not missing, f"Missing CONTRACT 1 keys in demo mode: {missing}"

    def test_demo_mode_default_company_name_is_apex(self):
        """Default demo company should be Apex Textiles."""
        result = run_pipeline([], demo_mode=True)
        assert "Apex" in result["company_name"]

    def test_demo_mode_overrides_company_name(self):
        """Caller can override company_name even in demo mode."""
        result = run_pipeline([], company_name="Test Corp Ltd", demo_mode=True)
        assert result["company_name"] == "Test Corp Ltd"

    def test_demo_mode_overrides_gstin(self):
        """Caller can override GSTIN even in demo mode."""
        result = run_pipeline([], gstin="29ABCDE1234F1Z5", demo_mode=True)
        assert result["gstin"] == "29ABCDE1234F1Z5"

    def test_demo_mode_does_not_mutate_mock_data(self):
        """Demo mode must not modify the original APEX_TEXTILES_DOC_REPORT."""
        original_company = APEX_TEXTILES_DOC_REPORT["company_name"]
        _ = run_pipeline([], company_name="Overridden Company", demo_mode=True)
        assert APEX_TEXTILES_DOC_REPORT["company_name"] == original_company

    def test_demo_mode_financials_are_present(self):
        """Demo financials must contain all 10 standard financial fields."""
        result = run_pipeline([], demo_mode=True)
        fin = result["financials"]
        required = {"revenue_cr", "ebitda_cr", "net_profit_cr", "total_assets_cr",
                    "total_liabilities_cr", "net_worth_cr", "dscr",
                    "current_ratio", "debt_to_equity", "interest_coverage"}
        missing = required - set(fin.keys())
        assert not missing, f"Missing financial fields in demo mode: {missing}"

    def test_demo_mode_has_early_warning_signals(self):
        """Demo output must include early_warning_signals (not empty for Apex)."""
        result = run_pipeline([], demo_mode=True)
        assert "early_warning_signals" in result
        assert isinstance(result["early_warning_signals"], list)
        assert len(result["early_warning_signals"]) > 0

    def test_demo_mode_has_trend_signals(self):
        """Demo output must include multi_year_financials and yoy_changes."""
        result = run_pipeline([], demo_mode=True)
        assert "multi_year_financials" in result
        assert "yoy_changes" in result
        assert len(result["multi_year_financials"]) >= 3   # FY22, FY23, FY24

    def test_demo_mode_false_does_not_early_return(self):
        """With demo_mode=False (default), pipeline does not use mock data."""
        # No files → should get default zeros not the Apex revenue of 42.5
        result = run_pipeline([], demo_mode=False)
        apex_revenue = APEX_TEXTILES_DOC_REPORT["financials"]["revenue_cr"]
        assert result["financials"]["revenue_cr"] != apex_revenue

    def test_demo_mode_confidence_above_zero(self):
        """Demo extraction_confidence should be a float > 0."""
        result = run_pipeline([], demo_mode=True)
        assert isinstance(result["extraction_confidence"], float)
        assert result["extraction_confidence"] > 0.0

    def test_demo_mode_gstin_default_is_apex(self):
        """Default demo GSTIN should match Apex Textiles GSTIN."""
        result = run_pipeline([], demo_mode=True)
        assert result["gstin"] == APEX_TEXTILES_DOC_REPORT["gstin"]
