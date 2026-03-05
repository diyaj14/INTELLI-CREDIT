"""
test_ews_generator.py — Tests for Feature 3: Early Warning Signals
====================================================================
Tests for EarlyWarningSignalGenerator covering all 6 EWS categories:
  1. Debt serviceability (DSCR)
  2. Liquidity (current ratio)
  3. Leverage (debt-to-equity)
  4. Profitability (net profit)
  5. GST compliance
  6. Banking behaviour (EMI vs balance, irregular credits)
"""

import pytest
from modules.document_intelligence.ews_generator import (
    EarlyWarningSignalGenerator, THRESHOLDS
)


# ──────────────────────────────────────────────────────────────────────────────
# Helper factories
# ──────────────────────────────────────────────────────────────────────────────

EWS_REQUIRED_KEYS = {"level", "signal", "category", "field", "threshold"}

def healthy_financials():
    return {
        "revenue_cr": 88.0, "ebitda_cr": 14.5, "net_profit_cr": 7.2,
        "total_assets_cr": 62.0, "total_liabilities_cr": 28.0, "net_worth_cr": 34.0,
        "dscr": 1.82, "current_ratio": 1.55, "debt_to_equity": 0.82,
        "interest_coverage": 4.10,
    }

def healthy_gst():
    return {"mismatch_pct": 3.1, "mismatch_flag": "GREEN",
            "circular_trading_flag": False, "revenue_inflation_flag": False,
            "gst_score": 20}

def healthy_bank():
    return {"avg_balance_cr": 4.20, "emi_outflow_monthly_cr": 0.65,
            "peak_balance_cr": 9.80, "regular_credits": True}

def apex_financials():
    return {
        "revenue_cr": 42.5, "ebitda_cr": 6.1, "net_profit_cr": 2.3,
        "total_assets_cr": 38.0, "total_liabilities_cr": 24.0, "net_worth_cr": 14.0,
        "dscr": 0.89, "current_ratio": 1.10, "debt_to_equity": 1.71,
        "interest_coverage": 2.40,
    }

def apex_gst():
    return {"mismatch_pct": 18.2, "mismatch_flag": "RED",
            "circular_trading_flag": True, "revenue_inflation_flag": False,
            "gst_score": 8}

def apex_bank():
    return {"avg_balance_cr": 1.80, "emi_outflow_monthly_cr": 0.42,
            "peak_balance_cr": 4.10, "regular_credits": True}

def make_gen(fin=None, gst=None, bank=None, trends=None):
    return EarlyWarningSignalGenerator(
        financials=fin or healthy_financials(),
        gst_analysis=gst or healthy_gst(),
        bank_statement=bank or healthy_bank(),
        trend_signals=trends or [],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Signal format validation
# ──────────────────────────────────────────────────────────────────────────────

class TestSignalFormat:

    def test_every_signal_has_required_keys(self):
        """Every signal in the output must have level, signal, category, field, threshold."""
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        assert len(signals) > 0
        for s in signals:
            missing = EWS_REQUIRED_KEYS - set(s.keys())
            assert not missing, f"Signal missing keys {missing}: {s}"

    def test_level_is_1_2_or_3(self):
        """All signal levels must be 1, 2, or 3."""
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        for sig in gen.generate():
            assert sig["level"] in (1, 2, 3), f"Invalid level in signal: {sig}"

    def test_signals_sorted_highest_severity_first(self):
        """Output is sorted: Level 3 first, then 2, then 1."""
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        levels = [s["level"] for s in signals]
        assert levels == sorted(levels, reverse=True), \
            f"Signals not sorted by severity: {levels}"

    def test_no_duplicate_field_level_pairs(self):
        """No two signals should have the same (level, field) pair."""
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        seen = set()
        for s in signals:
            key = (s["level"], s["field"])
            assert key not in seen, f"Duplicate signal: {key}"
            seen.add(key)


# ──────────────────────────────────────────────────────────────────────────────
# Debt serviceability (DSCR)
# ──────────────────────────────────────────────────────────────────────────────

class TestDSCR:

    def test_dscr_below_1_gives_level2(self):
        fin = {**healthy_financials(), "dscr": 0.89}
        signals = make_gen(fin=fin).generate()
        dscr_signals = [s for s in signals if s["field"] == "dscr"]
        assert any(s["level"] == 2 for s in dscr_signals)

    def test_dscr_1_to_1_25_gives_level1(self):
        fin = {**healthy_financials(), "dscr": 1.10}
        signals = make_gen(fin=fin).generate()
        dscr_signals = [s for s in signals if s["field"] == "dscr"]
        assert any(s["level"] == 1 for s in dscr_signals)

    def test_dscr_above_threshold_no_signal(self):
        fin = {**healthy_financials(), "dscr": 1.82}
        signals = make_gen(fin=fin).generate()
        dscr_signals = [s for s in signals if s["field"] == "dscr"]
        assert len(dscr_signals) == 0, f"Unexpected DSCR signals for healthy DSCR: {dscr_signals}"

    def test_dscr_none_skipped_gracefully(self):
        fin = {**healthy_financials(), "dscr": None}
        signals = make_gen(fin=fin).generate()   # should not crash
        assert isinstance(signals, list)


# ──────────────────────────────────────────────────────────────────────────────
# Liquidity (Current Ratio)
# ──────────────────────────────────────────────────────────────────────────────

class TestCurrentRatio:

    def test_cr_below_1_gives_level2(self):
        fin = {**healthy_financials(), "current_ratio": 0.85}
        signals = make_gen(fin=fin).generate()
        assert any(s["field"] == "current_ratio" and s["level"] == 2 for s in signals)

    def test_cr_1_to_133_gives_level1(self):
        fin = {**healthy_financials(), "current_ratio": 1.10}
        signals = make_gen(fin=fin).generate()
        assert any(s["field"] == "current_ratio" and s["level"] == 1 for s in signals)

    def test_cr_above_133_no_signal(self):
        fin = {**healthy_financials(), "current_ratio": 1.55}
        signals = make_gen(fin=fin).generate()
        assert not any(s["field"] == "current_ratio" for s in signals)


# ──────────────────────────────────────────────────────────────────────────────
# Profitability
# ──────────────────────────────────────────────────────────────────────────────

class TestProfitability:

    def test_net_loss_gives_level3(self):
        fin = {**healthy_financials(), "net_profit_cr": -2.5}
        signals = make_gen(fin=fin).generate()
        np_signals = [s for s in signals if s["field"] == "net_profit_cr"]
        assert any(s["level"] == 3 for s in np_signals), \
            f"Net loss should produce Level 3 signal, got: {np_signals}"

    def test_zero_profit_gives_level2(self):
        fin = {**healthy_financials(), "net_profit_cr": 0}
        signals = make_gen(fin=fin).generate()
        np_signals = [s for s in signals if s["field"] == "net_profit_cr"]
        assert any(s["level"] == 2 for s in np_signals)

    def test_healthy_profit_no_signal(self):
        fin = {**healthy_financials(), "net_profit_cr": 7.2, "revenue_cr": 88.0}
        signals = make_gen(fin=fin).generate()
        np_signals = [s for s in signals if s["field"] == "net_profit_cr"]
        assert len(np_signals) == 0


# ──────────────────────────────────────────────────────────────────────────────
# GST Compliance
# ──────────────────────────────────────────────────────────────────────────────

class TestGSTCompliance:

    def test_mismatch_above_15pct_gives_level2(self):
        gst = {**healthy_gst(), "mismatch_pct": 18.2}
        signals = make_gen(gst=gst).generate()
        assert any(s["field"] == "gst_mismatch_pct" and s["level"] == 2 for s in signals)

    def test_mismatch_5_to_15pct_gives_level1(self):
        gst = {**healthy_gst(), "mismatch_pct": 9.0}
        signals = make_gen(gst=gst).generate()
        assert any(s["field"] == "gst_mismatch_pct" and s["level"] == 1 for s in signals)

    def test_mismatch_below_5pct_no_signal(self):
        gst = {**healthy_gst(), "mismatch_pct": 3.1}
        signals = make_gen(gst=gst).generate()
        assert not any(s["field"] == "gst_mismatch_pct" for s in signals)

    def test_circular_trading_gives_level2(self):
        gst = {**healthy_gst(), "circular_trading_flag": True}
        signals = make_gen(gst=gst).generate()
        assert any(s["field"] == "circular_trading_flag" and s["level"] == 2 for s in signals)

    def test_revenue_inflation_gives_level2(self):
        gst = {**healthy_gst(), "revenue_inflation_flag": True}
        signals = make_gen(gst=gst).generate()
        assert any(s["field"] == "revenue_inflation_flag" and s["level"] == 2 for s in signals)

    def test_low_gst_score_gives_signal(self):
        gst = {**healthy_gst(), "gst_score": 8}
        signals = make_gen(gst=gst).generate()
        assert any(s["field"] == "gst_score" and s["level"] == 2 for s in signals)


# ──────────────────────────────────────────────────────────────────────────────
# Banking Behaviour
# ──────────────────────────────────────────────────────────────────────────────

class TestBankingBehaviour:

    def test_emi_exceeds_balance_gives_level2(self):
        bank = {"avg_balance_cr": 0.50, "emi_outflow_monthly_cr": 0.60,
                "peak_balance_cr": 1.0, "regular_credits": True}
        signals = make_gen(bank=bank).generate()
        assert any(s["field"] == "emi_outflow_monthly_cr" and s["level"] == 2 for s in signals)

    def test_emi_50pct_of_balance_gives_level1(self):
        bank = {"avg_balance_cr": 1.80, "emi_outflow_monthly_cr": 0.95,
                "peak_balance_cr": 4.0, "regular_credits": True}
        signals = make_gen(bank=bank).generate()
        assert any(s["field"] == "emi_outflow_monthly_cr" and s["level"] == 1 for s in signals)

    def test_irregular_credits_gives_level1(self):
        bank = {**healthy_bank(), "regular_credits": False}
        signals = make_gen(bank=bank).generate()
        assert any(s["field"] == "regular_credits" and s["level"] == 1 for s in signals)

    def test_healthy_bank_no_banking_signals(self):
        signals = make_gen(bank=healthy_bank()).generate()
        banking_signals = [s for s in signals if s["category"] == "banking_behaviour"]
        assert len(banking_signals) == 0, f"Unexpected banking signals: {banking_signals}"


# ──────────────────────────────────────────────────────────────────────────────
# Healthy Company — Zero Signals
# ──────────────────────────────────────────────────────────────────────────────

class TestHealthyCompany:

    def test_sunrise_foods_zero_ews_signals(self):
        """Sunrise Foods (healthy company) should produce no EWS signals."""
        signals = make_gen(
            fin=healthy_financials(),
            gst=healthy_gst(),
            bank=healthy_bank(),
            trends=[],
        ).generate()
        # Sunrise Foods is healthy — should have no Level 2 or 3 signals
        high_severity = [s for s in signals if s["level"] >= 2]
        assert len(high_severity) == 0, f"Healthy company got L2/L3 signals: {high_severity}"


# ──────────────────────────────────────────────────────────────────────────────
# Apex Textiles — Multiple Signals Expected
# ──────────────────────────────────────────────────────────────────────────────

class TestApexTextiles:

    def test_apex_textiles_generates_multiple_signals(self):
        """Apex Textiles high-risk scenario should fire multiple EWS signals."""
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        assert len(signals) >= 3, f"Expected >=3 signals for Apex Textiles, got {len(signals)}"

    def test_apex_has_level2_dscr_signal(self):
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        assert any(s["field"] == "dscr" and s["level"] == 2 for s in signals)

    def test_apex_has_gst_mismatch_signal(self):
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        assert any(s["field"] == "gst_mismatch_pct" and s["level"] == 2 for s in signals)

    def test_apex_has_circular_trading_signal(self):
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank())
        signals = gen.generate()
        assert any(s["field"] == "circular_trading_flag" and s["level"] == 2 for s in signals)

    def test_apex_trend_signals_merged(self):
        """Trend signals from Feature 1 should be merged into EWS output."""
        trend = [{"level": 2, "signal": "Revenue declining 2 years",
                  "category": "revenue_trend", "field": "revenue_cr"}]
        gen = make_gen(fin=apex_financials(), gst=apex_gst(), bank=apex_bank(), trends=trend)
        signals = gen.generate()
        assert any(s["field"] == "revenue_cr" for s in signals)

    def test_pipeline_contract_has_ews_key(self):
        """document_pipeline output must include early_warning_signals key."""
        from modules.document_intelligence.mock_data import APEX_TEXTILES_DOC_REPORT
        assert "early_warning_signals" in APEX_TEXTILES_DOC_REPORT
        assert isinstance(APEX_TEXTILES_DOC_REPORT["early_warning_signals"], list)
        assert len(APEX_TEXTILES_DOC_REPORT["early_warning_signals"]) > 0
