"""
test_financial_extractor_trends.py — Tests for Feature 1: Multi-Year Trend Analysis
======================================================================================
Tests for:
  - _detect_year_columns(): fiscal year header parsing
  - extract_multi_year(): multi-year metric extraction from comparative tables
  - compute_yoy_changes(): YoY % delta computation
  - generate_trend_signals(): RBI EWS-aligned signal generation
"""

import pytest
from modules.document_intelligence.financial_extractor import FinancialExtractor


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_extractor(text_pages: dict, tables: list = None) -> FinancialExtractor:
    """Creates a FinancialExtractor from raw text pages (no real PDF needed)."""
    return FinancialExtractor(raw_text=text_pages, tables=tables or [])


# ──────────────────────────────────────────────────────────────────────────────
# _detect_year_columns
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectYearColumns:

    def test_fy_dash_format(self):
        """Detects FY2022-23 / FY2023-24 style headers."""
        extractor = make_extractor({1: "FY2022-23  FY2023-24"})
        years = extractor._detect_year_columns("FY2022-23  FY2023-24")
        assert "FY23" in years
        assert "FY24" in years

    def test_short_fy_format(self):
        """Detects FY 22-23 / FY 23-24 (space-separated short form)."""
        extractor = make_extractor({1: "FY 22-23  FY 23-24"})
        years = extractor._detect_year_columns("FY 22-23  FY 23-24")
        assert "FY23" in years
        assert "FY24" in years

    def test_standalone_year_range_format(self):
        """Detects 2022-23 / 2023-24 without FY prefix."""
        extractor = make_extractor({1: "2022-23   2023-24"})
        years = extractor._detect_year_columns("2022-23   2023-24")
        assert len(years) >= 2, f"Expected >=2 years, got: {years}"

    def test_year_ended_march_format(self):
        """Detects 'Year ended March 2023' / 'Year ended March 2024' style."""
        text = "Year ended March 2023   Year ended March 2024"
        extractor = make_extractor({1: text})
        years = extractor._detect_year_columns(text)
        assert "FY23" in years or "FY24" in years

    def test_no_year_headers_returns_empty(self):
        """Pages without fiscal year headers return empty list."""
        extractor = make_extractor({1: "Director's Report — Management Discussion"})
        years = extractor._detect_year_columns("Director's Report — Management Discussion")
        assert years == []

    def test_years_sorted_chronologically(self):
        """Year labels are returned in sorted (chronological) order."""
        text = "FY 23-24  FY 21-22  FY 22-23"
        extractor = make_extractor({1: text})
        years = extractor._detect_year_columns(text)
        assert years == sorted(years)


# ──────────────────────────────────────────────────────────────────────────────
# compute_yoy_changes
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeYoY:

    def test_positive_growth(self):
        """Revenue growing from 42 → 46.2 → +10% YoY."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"revenue_cr": 42.0},
            "FY24": {"revenue_cr": 46.2},
        }
        yoy = extractor.compute_yoy_changes(multi)
        assert "revenue_cr" in yoy
        assert len(yoy["revenue_cr"]) == 1
        assert abs(yoy["revenue_cr"][0]["pct_change"] - 10.0) < 0.1

    def test_negative_decline(self):
        """Revenue declining from 51.2 → 42.5 should give negative pct_change."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 51.2},
            "FY23": {"revenue_cr": 46.8},
            "FY24": {"revenue_cr": 42.5},
        }
        yoy = extractor.compute_yoy_changes(multi)
        for entry in yoy["revenue_cr"]:
            assert entry["pct_change"] < 0, "Declining revenue should produce negative YoY"

    def test_three_year_produces_two_yoy_entries(self):
        """Three years of data → two YoY entries per metric."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 51.2},
            "FY23": {"revenue_cr": 46.8},
            "FY24": {"revenue_cr": 42.5},
        }
        yoy = extractor.compute_yoy_changes(multi)
        assert len(yoy["revenue_cr"]) == 2

    def test_missing_field_in_one_year_skipped(self):
        """If a field is missing in one year, that pair is skipped (no crash)."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 51.2},
            "FY23": {},   # missing revenue
            "FY24": {"revenue_cr": 42.5},
        }
        yoy = extractor.compute_yoy_changes(multi)
        # Should not crash; entries may be partial
        assert isinstance(yoy, dict)

    def test_from_and_to_year_labels_correct(self):
        """YoY entries carry correct from_year and to_year labels."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"net_profit_cr": 4.1},
            "FY23": {"net_profit_cr": 3.2},
        }
        yoy = extractor.compute_yoy_changes(multi)
        entry = yoy["net_profit_cr"][0]
        assert entry["from_year"] == "FY22"
        assert entry["to_year"] == "FY23"


# ──────────────────────────────────────────────────────────────────────────────
# generate_trend_signals
# ──────────────────────────────────────────────────────────────────────────────

class TestGenerateTrendSignals:

    def test_declining_revenue_two_years_is_level2(self):
        """Revenue declining 2+ years → Level 2 signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 51.2},
            "FY23": {"revenue_cr": 46.8},
            "FY24": {"revenue_cr": 42.5},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        revenue_signals = [s for s in signals if s["field"] == "revenue_cr"]
        assert len(revenue_signals) >= 1
        assert revenue_signals[0]["level"] == 2

    def test_declining_revenue_one_year_is_level1(self):
        """Revenue declining only 1 year → Level 1 signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"revenue_cr": 79.5},
            "FY24": {"revenue_cr": 42.5},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        revenue_signals = [s for s in signals if s["field"] == "revenue_cr"]
        assert any(s["level"] == 1 for s in revenue_signals)

    def test_dscr_below_one_is_level2(self):
        """DSCR 0.89 (<1.0) → Level 2 signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"dscr": 1.31},
            "FY24": {"dscr": 0.89},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        dscr_signals = [s for s in signals if s["field"] == "dscr"]
        assert any(s["level"] == 2 for s in dscr_signals), f"Got: {dscr_signals}"

    def test_dscr_between_1_and_1_25_is_level1(self):
        """DSCR 1.08 (between 1.0 and 1.25) → Level 1 signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"dscr": 1.31},
            "FY24": {"dscr": 1.08},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        dscr_signals = [s for s in signals if s["field"] == "dscr"]
        # Level 1 (below 1.25) should appear
        assert any(s["level"] == 1 for s in dscr_signals)

    def test_net_loss_is_level3(self):
        """Negative net profit in latest year → Level 3 (Stress) signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"net_profit_cr": 3.2},
            "FY24": {"net_profit_cr": -1.5},   # net loss!
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        np_signals = [s for s in signals if s["field"] == "net_profit_cr"]
        assert any(s["level"] == 3 for s in np_signals)

    def test_current_ratio_below_1_33_is_level1(self):
        """Current ratio 1.10 < 1.33 → Level 1 signal."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY23": {"current_ratio": 1.40},
            "FY24": {"current_ratio": 1.10},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        cr_signals = [s for s in signals if s["field"] == "current_ratio"]
        assert any(s["level"] == 1 for s in cr_signals)

    def test_healthy_company_no_critical_signals(self):
        """Sunrise Foods-style improving metrics → no Level 2/3 signals."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 71.2, "dscr": 1.55, "current_ratio": 1.38, "net_profit_cr": 5.1},
            "FY23": {"revenue_cr": 79.5, "dscr": 1.68, "current_ratio": 1.46, "net_profit_cr": 6.1},
            "FY24": {"revenue_cr": 88.0, "dscr": 1.82, "current_ratio": 1.55, "net_profit_cr": 7.2},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        high_severity = [s for s in signals if s["level"] >= 2]
        assert len(high_severity) == 0, f"Healthy company should have no L2/3 signals: {high_severity}"

    def test_single_year_data_returns_no_signals(self):
        """Only 1 year of data → cannot compute trends → empty signals list."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY24": {"revenue_cr": 42.5, "dscr": 0.89},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        # With only 1 year, cannot produce revenue trend signals
        trend_signals = [s for s in signals if s["category"] == "revenue_trend"]
        assert len(trend_signals) == 0

    def test_signals_have_required_fields(self):
        """Every signal dict must have: level, signal, category, field."""
        extractor = make_extractor({1: ""})
        multi = {
            "FY22": {"revenue_cr": 51.2, "dscr": 1.31, "current_ratio": 1.40, "net_profit_cr": 4.1},
            "FY23": {"revenue_cr": 46.8, "dscr": 1.08, "current_ratio": 1.22, "net_profit_cr": 3.2},
            "FY24": {"revenue_cr": 42.5, "dscr": 0.89, "current_ratio": 1.10, "net_profit_cr": 2.3},
        }
        yoy = extractor.compute_yoy_changes(multi)
        signals = extractor.generate_trend_signals(multi, yoy)
        assert len(signals) > 0
        for sig in signals:
            assert "level" in sig, f"Missing 'level' in signal: {sig}"
            assert "signal" in sig, f"Missing 'signal' in signal: {sig}"
            assert "category" in sig, f"Missing 'category' in signal: {sig}"
            assert "field" in sig, f"Missing 'field' in signal: {sig}"
            assert sig["level"] in (1, 2, 3), f"Level must be 1, 2, or 3: {sig}"


# ──────────────────────────────────────────────────────────────────────────────
# extract_all() output structure (integration check)
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractAllTrendOutput:

    def test_extract_all_returns_trend_keys(self):
        """extract_all() must return multi_year_financials, yoy_changes, trend_signals."""
        # Minimal text — won't extract much, but should not crash and should return keys
        extractor = make_extractor({
            1: "Revenue from Operations 42.50 Cr\nProfit after tax 2.30 Cr\n"
               "Total Assets 38.00 Cr\nNet Worth 14.00 Cr",
        })
        result = extractor.extract_all(use_llm_fallback=False)
        assert "multi_year_financials" in result
        assert "yoy_changes" in result
        assert "trend_signals" in result

    def test_extract_all_trend_signals_is_list(self):
        """trend_signals output is always a list (may be empty, never None)."""
        extractor = make_extractor({1: "Revenue from Operations 42.50 Cr"})
        result = extractor.extract_all(use_llm_fallback=False)
        assert isinstance(result["trend_signals"], list)

    def test_extract_all_multi_year_is_dict(self):
        """multi_year_financials is always a dict (may have 0 or more year keys)."""
        extractor = make_extractor({1: "Revenue from Operations 42.50 Cr"})
        result = extractor.extract_all(use_llm_fallback=False)
        assert isinstance(result["multi_year_financials"], dict)

    def test_extract_all_with_comparative_table_text(self):
        """Text containing FY column headers should produce multi-year data."""
        text = (
            "Statement of Profit and Loss\n"
            "FY 2022-23    FY 2023-24\n"
            "Revenue from Operations  46.80   42.50\n"
            "Profit after tax          3.20    2.30\n"
        )
        extractor = make_extractor({3: text})
        result = extractor.extract_all(use_llm_fallback=False)
        multi = result["multi_year_financials"]
        # At least one year should be detected
        assert len(multi) >= 1
