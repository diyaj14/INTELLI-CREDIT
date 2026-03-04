"""
test_source_citations.py — Tests for Feature 2: Rich Source Citations
======================================================================
Tests for:
  - _make_citation(): structured citation object format
  - extract_field_regex(): stores structured citation in _citations_structured
  - extract_field_llm(): stores structured citation with llm method
  - compute_ratios(): stores structured citations for derived ratios
  - extract_all(): returns source_citations_structured with required fields
"""

import pytest
from modules.document_intelligence.financial_extractor import FinancialExtractor


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

CITATION_REQUIRED_KEYS = {"value", "unit", "source_page", "source_statement",
                           "confidence", "context", "method"}

VALID_METHODS = {"regex", "table", "llm", "computed", "default"}


def make_extractor(text_pages: dict) -> FinancialExtractor:
    return FinancialExtractor(raw_text=text_pages, tables=[])


# ──────────────────────────────────────────────────────────────────────────────
# _make_citation
# ──────────────────────────────────────────────────────────────────────────────

class TestMakeCitation:

    def test_has_all_required_keys(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(42.5, "revenue_cr", 3, "Revenue 42.5 Cr", "regex")
        assert CITATION_REQUIRED_KEYS <= set(cit.keys()), f"Missing keys: {CITATION_REQUIRED_KEYS - set(cit.keys())}"

    def test_crore_field_has_cr_unit(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(42.5, "revenue_cr", 3, "ctx", "regex")
        assert cit["unit"] == "Cr"

    def test_ratio_field_has_ratio_unit(self):
        extractor = make_extractor({1: ""})
        for field in ("current_ratio", "debt_to_equity", "interest_coverage", "dscr"):
            cit = extractor._make_citation(1.5, field, None, "ctx", "computed")
            assert cit["unit"] == "ratio", f"Expected 'ratio' unit for {field}, got '{cit['unit']}'"

    def test_regex_method_has_high_confidence(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(42.5, "revenue_cr", 3, "ctx", "regex")
        assert cit["confidence"] >= 0.90, f"Regex confidence should be >=0.90, got {cit['confidence']}"

    def test_llm_method_has_lower_confidence(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(42.5, "revenue_cr", None, "ctx", "llm")
        assert cit["confidence"] < 0.80, f"LLM confidence should be <0.80, got {cit['confidence']}"

    def test_default_method_has_lowest_confidence(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(0.0, "revenue_cr", None, "ctx", "default")
        assert cit["confidence"] <= 0.25

    def test_value_is_rounded(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(42.123456, "revenue_cr", 3, "ctx", "regex")
        assert cit["value"] == round(42.123456, 3)

    def test_context_is_truncated_to_120_chars(self):
        extractor = make_extractor({1: ""})
        long_ctx = "x" * 200
        cit = extractor._make_citation(1.0, "revenue_cr", 1, long_ctx, "regex")
        assert len(cit["context"]) <= 120

    def test_source_page_none_has_computed_statement(self):
        extractor = make_extractor({1: ""})
        cit = extractor._make_citation(1.71, "debt_to_equity", None, "ctx", "computed")
        assert cit["source_page"] is None
        assert cit["source_statement"] == "Computed"

    def test_method_value_is_valid(self):
        extractor = make_extractor({1: ""})
        for method in VALID_METHODS:
            cit = extractor._make_citation(1.0, "revenue_cr", None, "ctx", method)
            assert cit["method"] == method


# ──────────────────────────────────────────────────────────────────────────────
# extract_all() — source_citations_structured in output
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractAllStructuredCitations:

    def test_extract_all_returns_structured_citations_key(self):
        """extract_all() must include source_citations_structured in return dict."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\n"
               "Profit after tax 2.30 Cr\n"
               "Total Assets 38.00 Cr\nTotal Liabilities 24.00 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        assert "source_citations_structured" in result, \
            "Missing source_citations_structured in extract_all() output"

    def test_structured_citations_covers_all_contract1_fields(self):
        """source_citations_structured has an entry for all 10 CONTRACT 1 fields."""
        required_fields = {
            "revenue_cr", "ebitda_cr", "net_profit_cr",
            "total_assets_cr", "total_liabilities_cr", "net_worth_cr",
            "dscr", "current_ratio", "debt_to_equity", "interest_coverage",
        }
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\nProfit after tax 2.30 Cr\n"
               "Total Assets 38.00 Cr\nTotal Liabilities 24.00 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        structured = result["source_citations_structured"]
        missing = required_fields - set(structured.keys())
        assert not missing, f"Missing fields in source_citations_structured: {missing}"

    def test_each_structured_citation_has_required_fields(self):
        """Every citation in source_citations_structured must have all 7 required keys."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\nTotal Assets 38.00 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        for field, cit in result["source_citations_structured"].items():
            assert CITATION_REQUIRED_KEYS <= set(cit.keys()), \
                f"Citation for '{field}' missing keys: {CITATION_REQUIRED_KEYS - set(cit.keys())}"

    def test_regex_extracted_field_has_high_confidence(self):
        """A field extracted via regex should have confidence >= 0.90."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        structured = result["source_citations_structured"]
        if structured["revenue_cr"]["method"] == "regex":
            assert structured["revenue_cr"]["confidence"] >= 0.90

    def test_computed_ratio_has_computed_method(self):
        """DSCR / current_ratio / D/E are computed, should show method='computed'."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\nTotal Assets 38.00 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        structured = result["source_citations_structured"]
        computed_fields = {"dscr", "current_ratio", "debt_to_equity", "interest_coverage"}
        for field in computed_fields:
            if field in structured:
                assert structured[field]["method"] in ("computed", "default"), \
                    f"Expected computed/default method for {field}, got {structured[field]['method']}"

    def test_source_citations_plain_still_present(self):
        """Backward-compatible plain source_citations must still exist."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        assert "source_citations" in result
        assert isinstance(result["source_citations"], dict)
        assert len(result["source_citations"]) > 0

    def test_llm_extracted_field_has_low_confidence(self):
        """Fields extracted by Gemini LLM fallback should have confidence 0.70."""
        extractor = make_extractor({1: ""})
        # Manually inject an LLM-method citation
        cit = extractor._make_citation(5.0, "ebitda_cr", None, "LLM extraction via Gemini Flash", "llm")
        extractor._citations_structured["ebitda_cr"] = cit
        assert cit["confidence"] == 0.70

    def test_unit_for_crore_fields_is_cr(self):
        """All _cr fields should have unit='Cr' in their structured citation."""
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\nProfit after tax 2.30 Cr\n"
               "Total Assets 38.00 Cr\nTotal Liabilities 24.00 Cr\n"
        })
        result = extractor.extract_all(use_llm_fallback=False)
        structured = result["source_citations_structured"]
        cr_fields = [f for f in structured if f.endswith("_cr")]
        for field in cr_fields:
            assert structured[field]["unit"] == "Cr", \
                f"Expected unit='Cr' for {field}, got '{structured[field]['unit']}'"
