"""
tests/test_document_pipeline.py
================================
Integration tests for run_pipeline() and FileClassifier.
Uses real fixture files from tests/fixtures/ where possible.
Does NOT call Gemini (use_llm_fallback=False in all tests).

Run: pytest tests/test_document_pipeline.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.document_intelligence.document_pipeline import (
    run_pipeline,
    FileClassifier,
    _default_financials,
    _default_gst_analysis,
    _default_bank_statement,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
GSTR3B_PATH  = os.path.join(FIXTURES_DIR, "sample_gstr3b.csv")
GSTR2A_PATH  = os.path.join(FIXTURES_DIR, "sample_gstr2a.csv")
BANK_PATH    = os.path.join(FIXTURES_DIR, "sample_bank_statement.csv")

# CONTRACT 1 required keys
CONTRACT1_KEYS = {
    "company_name", "gstin", "financials", "gst_analysis",
    "bank_statement", "extraction_confidence", "source_citations",
}
FINANCIALS_KEYS = {
    "revenue_cr", "ebitda_cr", "net_profit_cr", "total_assets_cr",
    "total_liabilities_cr", "net_worth_cr", "dscr",
    "current_ratio", "debt_to_equity", "interest_coverage",
}
GST_KEYS = {
    "mismatch_pct", "mismatch_flag", "circular_trading_flag",
    "revenue_inflation_flag", "gst_score",
}
BANK_KEYS = {"avg_balance_cr", "emi_outflow_monthly_cr", "peak_balance_cr", "regular_credits"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: FileClassifier
# ─────────────────────────────────────────────────────────────────────────────

class TestFileClassifier:

    @pytest.mark.parametrize("filename, expected", [
        ("annual_report_FY24.pdf",       "annual_report"),
        ("balance_sheet.pdf",            "annual_report"),
        ("itr_FY2024.pdf",               "annual_report"),
        ("gstr3b_FY24.xlsx",             "gstr3b"),
        ("GSTR-3B_Apr2023.xlsx",         "gstr3b"),
        ("gstr2a_FY24.xlsx",             "gstr2a"),
        ("GSTR-2A_FY24.csv",             "gstr2a"),
        ("bank_statement.csv",           "bank_statement"),
        ("hdfc_account_statement.csv",   "bank_statement"),
        ("current_account.xlsx",         "bank_statement"),
        ("sample_gstr3b.csv",            "gstr3b"),
        ("sample_gstr2a.csv",            "gstr2a"),
        ("sample_bank_statement.csv",    "bank_statement"),
    ])
    def test_classifier_maps_filenames(self, filename, expected):
        clf = FileClassifier()
        # Use a fake path — only filename matters
        result = clf.classify(f"e:/fake/{filename}")
        assert result == expected, \
            f"'{filename}' → expected '{expected}', got '{result}'"

    def test_unknown_extension_returns_unknown(self):
        clf = FileClassifier()
        result = clf.classify("e:/fake/data.zip")
        assert result == "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Default fallback dicts
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultDicts:

    def test_default_financials_has_all_keys(self):
        d = _default_financials()
        missing = FINANCIALS_KEYS - d.keys()
        assert not missing, f"Missing: {missing}"

    def test_default_gst_has_all_keys(self):
        d = _default_gst_analysis()
        missing = GST_KEYS - d.keys()
        assert not missing, f"Missing: {missing}"

    def test_default_bank_has_all_keys(self):
        d = _default_bank_statement()
        missing = BANK_KEYS - d.keys()
        assert not missing, f"Missing: {missing}"

    def test_default_gst_flag_is_green(self):
        d = _default_gst_analysis()
        assert d["mismatch_flag"] == "GREEN"

    def test_default_gst_score_is_20(self):
        d = _default_gst_analysis()
        assert d["gst_score"] == 20


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_pipeline (no annual report — partial pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPipelinePartial:

    def test_pipeline_with_only_gst_files(self):
        result = run_pipeline(
            uploaded_files=[GSTR3B_PATH, GSTR2A_PATH],
            company_name="Test Co",
            gstin="27TESTGSTIN00001",
            use_llm_fallback=False,
        )
        missing = CONTRACT1_KEYS - result.keys()
        assert not missing, f"Missing CONTRACT 1 keys: {missing}"

    def test_pipeline_with_only_bank_statement(self):
        result = run_pipeline(
            uploaded_files=[BANK_PATH],
            company_name="Test Co",
            gstin="27TESTGSTIN00001",
            use_llm_fallback=False,
        )
        missing = CONTRACT1_KEYS - result.keys()
        assert not missing, f"Missing CONTRACT 1 keys: {missing}"

    def test_pipeline_with_empty_file_list(self):
        result = run_pipeline(
            uploaded_files=[],
            company_name="Ghost Company",
            gstin="",
            use_llm_fallback=False,
        )
        missing = CONTRACT1_KEYS - result.keys()
        assert not missing, f"Missing CONTRACT 1 keys even with no files: {missing}"

    def test_confidence_is_0_with_no_files(self):
        result = run_pipeline([], "Ghost", "", use_llm_fallback=False)
        # No files → completeness=0, fin_confidence=0 → expect 0
        assert result["extraction_confidence"] == 0.0

    def test_pipeline_with_nonexistent_file_does_not_crash(self):
        result = run_pipeline(
            uploaded_files=["/fake/nonexistent.pdf", BANK_PATH],
            company_name="Resilient Co",
            gstin="",
            use_llm_fallback=False,
        )
        assert "company_name" in result  # completes without crash


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_pipeline (GST + Bank — no PDF annual report)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPipelineGSTAndBank:

    @pytest.fixture(scope="class")
    def result(self):
        return run_pipeline(
            uploaded_files=[GSTR3B_PATH, GSTR2A_PATH, BANK_PATH],
            company_name="Apex Textiles Pvt Ltd",
            gstin="27AAPCA5678H1Z2",
            use_llm_fallback=False,
        )

    def test_contract1_all_keys_present(self, result):
        missing = CONTRACT1_KEYS - result.keys()
        assert not missing, f"Missing: {missing}"

    def test_financials_all_keys_present(self, result):
        missing = FINANCIALS_KEYS - result["financials"].keys()
        assert not missing, f"Missing financials keys: {missing}"

    def test_gst_all_keys_present(self, result):
        missing = GST_KEYS - result["gst_analysis"].keys()
        assert not missing, f"Missing gst_analysis keys: {missing}"

    def test_bank_all_keys_present(self, result):
        missing = BANK_KEYS - result["bank_statement"].keys()
        assert not missing, f"Missing bank_statement keys: {missing}"

    def test_company_name_preserved(self, result):
        assert result["company_name"] == "Apex Textiles Pvt Ltd"

    def test_gstin_preserved(self, result):
        assert result["gstin"] == "27AAPCA5678H1Z2"

    def test_gst_flag_is_red_for_fixture(self, result):
        assert result["gst_analysis"]["mismatch_flag"] == "RED"

    def test_gst_score_at_most_10_for_fixture(self, result):
        assert result["gst_analysis"]["gst_score"] <= 10

    def test_bank_avg_balance_positive(self, result):
        assert result["bank_statement"]["avg_balance_cr"] > 0

    def test_bank_regular_credits_true(self, result):
        assert result["bank_statement"]["regular_credits"] is True

    def test_confidence_between_0_and_1(self, result):
        c = result["extraction_confidence"]
        assert 0.0 <= c <= 1.0, f"Confidence {c} out of range"

    def test_confidence_partial_without_annual_report(self, result):
        """With GST + bank but no annual report, confidence < 0.5."""
        # completeness = 0.67 (2/3), fin_confidence = 0 → weighted ~0.33
        assert result["extraction_confidence"] < 0.5

    def test_source_citations_is_dict(self, result):
        assert isinstance(result["source_citations"], dict)

    def test_all_financial_values_numeric(self, result):
        for k, v in result["financials"].items():
            assert isinstance(v, (int, float)), f"financials.{k} = {v} is not numeric"

    def test_regular_credits_is_bool(self, result):
        assert isinstance(result["bank_statement"]["regular_credits"], bool)
