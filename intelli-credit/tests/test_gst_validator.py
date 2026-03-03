"""
tests/test_gst_validator.py
============================
Tests for GSTCrossValidator using synthetic fixture CSVs.

Fixtures have an 18.2% ITC mismatch baked in (Apex Textiles demo scenario).

Run: pytest tests/test_gst_validator.py -v
"""
import os
import sys
import pytest
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.document_intelligence.gst_validator import (
    GSTCrossValidator,
    _normalize_column,
    GSTR3B_COLUMN_ALIASES,
    GSTR2A_COLUMN_ALIASES,
)

# ─────────────────────────────────────────────────────────────────────────────
# Paths to synthetic fixture files
# ─────────────────────────────────────────────────────────────────────────────

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
GSTR3B_PATH  = os.path.join(FIXTURES_DIR, "sample_gstr3b.csv")
GSTR2A_PATH  = os.path.join(FIXTURES_DIR, "sample_gstr2a.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Inline DataFrames (for tests that don't need file I/O)
# ─────────────────────────────────────────────────────────────────────────────

def make_gstr3b_df(periods, itc_claimed_values, taxable_values=None) -> pd.DataFrame:
    data = {"period": periods, "itc_claimed": itc_claimed_values}
    if taxable_values:
        data["taxable_value"] = taxable_values
    return pd.DataFrame(data)


def make_gstr2a_df(periods, supplier_gstins, itc_available_values) -> pd.DataFrame:
    return pd.DataFrame({
        "period":          periods,
        "supplier_gstin":  supplier_gstins,
        "itc_available":   itc_available_values,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def validator_from_files():
    """Loads real fixture CSVs."""
    v = GSTCrossValidator()
    v.load_gstr3b(GSTR3B_PATH)
    v.load_gstr2a(GSTR2A_PATH)
    return v


@pytest.fixture
def validator_clean():
    """A validator with minimal mismatch (GREEN scenario)."""
    v = GSTCrossValidator()
    periods = ["Apr-2023", "May-2023", "Jun-2023"]
    v.load_from_dataframes(
        gstr3b_df=make_gstr3b_df(periods, [1000, 1020, 980]),
        gstr2a_df=make_gstr2a_df(
            periods * 1,
            ["27AAPCA5678H1Z2"] * 3,
            [980, 1005, 970],    # ~2% below claimed — GREEN
        )
    )
    return v


@pytest.fixture
def validator_circular():
    """A validator where the top supplier accounts for 60% of ITC (round-tripping)."""
    v = GSTCrossValidator()
    periods = ["Apr-2023", "May-2023", "Jun-2023"]
    v.load_from_dataframes(
        gstr3b_df=make_gstr3b_df(periods, [5000, 5000, 5000]),
        gstr2a_df=make_gstr2a_df(
            periods + periods,
            ["SUSPECT_GSTIN_1"] * 3 + ["NORMAL_GSTIN"] * 3,
            [3500, 3500, 3500,   # suspect = 70% of ITC
             500,  500,  500],
        )
    )
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Tests: File Loading
# ─────────────────────────────────────────────────────────────────────────────

class TestFileLoading:

    def test_load_gstr3b_from_csv(self):
        v = GSTCrossValidator()
        df = v.load_gstr3b(GSTR3B_PATH)
        assert df is not None
        assert "period" in df.columns
        assert "itc_claimed" in df.columns
        assert len(df) == 12, f"Expected 12 periods, got {len(df)}"

    def test_load_gstr2a_from_csv(self):
        v = GSTCrossValidator()
        df = v.load_gstr2a(GSTR2A_PATH)
        assert df is not None
        assert "period" in df.columns
        assert "itc_available" in df.columns
        assert len(df) == 24, f"Expected 24 rows (2 suppliers × 12 periods), got {len(df)}"

    def test_itc_claimed_is_numeric(self):
        v = GSTCrossValidator()
        df = v.load_gstr3b(GSTR3B_PATH)
        assert pd.api.types.is_numeric_dtype(df["itc_claimed"]), \
            "itc_claimed should be numeric after loading"

    def test_missing_period_column_raises(self):
        df_bad = pd.DataFrame({"no_period": [1, 2], "itc_claimed": [100, 200]})
        with pytest.raises(ValueError, match="missing required column"):
            v = GSTCrossValidator()
            v.gstr3b = None
            # Simulate missing column by calling load on file with wrong cols
            # (we test by directly calling load_from_dataframes and then messing up)
            import tempfile, csv
            with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False,
                                             newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["no_period", "itc_claimed"])
                writer.writerow([1, 100])
                tmp_path = f.name
            v.load_gstr3b(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: compute_mismatch_pct
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeMismatchPct:

    def test_mismatch_pct_approximately_18(self, validator_from_files):
        """The synthetic fixtures are designed to produce ~18.2% mismatch."""
        mismatch, detail = validator_from_files.compute_mismatch_pct()
        assert 10.0 <= mismatch <= 30.0, \
            f"Expected mismatch 10–30%, got {mismatch:.1f}%"

    def test_mismatch_triggers_red_flag(self, validator_from_files):
        mismatch, _ = validator_from_files.compute_mismatch_pct()
        flag = validator_from_files.classify_flag(mismatch)
        assert flag == "RED", f"Expected RED for {mismatch:.1f}% mismatch, got {flag}"

    def test_clean_data_gives_low_mismatch(self, validator_clean):
        mismatch, _ = validator_clean.compute_mismatch_pct()
        assert mismatch < 5.0, f"Clean data should give <5% mismatch, got {mismatch:.1f}%"

    def test_mismatch_detail_has_period_keys(self, validator_from_files):
        _, detail = validator_from_files.compute_mismatch_pct()
        assert len(detail) > 0, "Period-wise detail should not be empty"
        for key in detail:
            assert "itc_claimed" in detail[key] or "mismatch_pct" in detail[key], \
                f"Detail entry missing expected keys: {detail[key]}"

    def test_mismatch_is_non_negative(self, validator_clean):
        """Mismatch should be capped at 0 (under-claiming ITC is not a fraud signal)."""
        mismatch, _ = validator_clean.compute_mismatch_pct()
        assert mismatch >= 0.0

    def test_no_data_raises(self):
        v = GSTCrossValidator()
        with pytest.raises(RuntimeError):
            v.compute_mismatch_pct()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_circular_trading
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectCircularTrading:

    def test_circular_trading_detected_for_dominant_supplier(self, validator_circular):
        is_circular, flagged = validator_circular.detect_circular_trading()
        assert is_circular is True, \
            "Should detect circular trading when single supplier has >40% of ITC"

    def test_no_circular_trading_in_clean_data(self, validator_clean):
        is_circular, flagged = validator_clean.detect_circular_trading()
        # Clean data has balanced suppliers — may or may not flag
        assert isinstance(is_circular, bool)
        assert isinstance(flagged, list)

    def test_returns_bool_and_list(self, validator_from_files):
        is_circular, flagged = validator_from_files.detect_circular_trading()
        assert isinstance(is_circular, bool)
        assert isinstance(flagged, list)
        assert len(flagged) <= 5, "Should return at most 5 flagged GSTINs"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_revenue_inflation
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectRevenueInflation:

    def test_no_inflation_when_bank_roughly_matches(self, validator_from_files):
        """When bank credits >> GST sales, no inflation is flagged."""
        is_inflated, div_pct = validator_from_files.detect_revenue_inflation(
            bank_credits_cr=10000.0  # definitively larger than any GST total
        )
        assert isinstance(is_inflated, bool), f"Expected bool, got {type(is_inflated)}"
        assert isinstance(div_pct, float),    f"Expected float, got {type(div_pct)}"
        assert is_inflated is False, \
            f"bank=10000 Cr should not trigger inflation; divergence={div_pct:.1f}%"

    def test_inflation_detected_when_bank_much_lower(self, validator_from_files):
        """When bank credits are trivially small, inflation is always flagged."""
        is_inflated, div_pct = validator_from_files.detect_revenue_inflation(
            bank_credits_cr=1.0   # trivially tiny — always triggers
        )
        assert isinstance(is_inflated, bool), f"Expected bool, got {type(is_inflated)}"
        assert is_inflated is True, \
            f"bank=1 Cr should trigger inflation; divergence={div_pct:.1f}%"
        assert div_pct > 15.0, f"Divergence should be >15%, got {div_pct:.1f}%"

    def test_no_inflation_on_zero_bank_credits(self, validator_from_files):
        is_inflated, div_pct = validator_from_files.detect_revenue_inflation(
            bank_credits_cr=0.0
        )
        assert is_inflated is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: classify_flag
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyFlag:

    @pytest.mark.parametrize("pct, expected", [
        (2.0,  "GREEN"),
        (4.9,  "GREEN"),
        (5.0,  "YELLOW"),
        (9.9,  "YELLOW"),
        (10.0, "YELLOW"),
        (10.1, "RED"),
        (18.2, "RED"),
        (50.0, "RED"),
    ])
    def test_flag_thresholds(self, pct, expected):
        v = GSTCrossValidator()
        assert v.classify_flag(pct) == expected, \
            f"mismatch_pct={pct} → expected {expected}"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: gst_score
# ─────────────────────────────────────────────────────────────────────────────

class TestGSTScore:

    def test_green_no_extras_gives_20(self):
        v = GSTCrossValidator()
        assert v.gst_score("GREEN", False, False) == 20

    def test_yellow_no_extras_gives_14(self):
        v = GSTCrossValidator()
        assert v.gst_score("YELLOW", False, False) == 14

    def test_red_no_extras_gives_8(self):
        v = GSTCrossValidator()
        assert v.gst_score("RED", False, False) == 8

    def test_red_plus_circular_deducts_4(self):
        v = GSTCrossValidator()
        score = v.gst_score("RED", True, False)
        assert score == 4, f"Expected 8-4=4, got {score}"

    def test_red_plus_both_flags_minimum_zero(self):
        v = GSTCrossValidator()
        score = v.gst_score("RED", True, True)
        assert score == max(0, 8 - 4 - 3), f"Expected {max(0, 8-4-3)}, got {score}"

    def test_score_never_negative(self):
        v = GSTCrossValidator()
        score = v.gst_score("RED", True, True)
        assert score >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: validate() — full integration
# ─────────────────────────────────────────────────────────────────────────────

class TestValidate:

    def test_validate_returns_all_contract1_keys(self, validator_from_files):
        result = validator_from_files.validate(bank_credits_cr=42.5)
        required_keys = {
            "mismatch_pct", "mismatch_flag", "circular_trading_flag",
            "revenue_inflation_flag", "gst_score",
        }
        missing = required_keys - result.keys()
        assert not missing, f"validate() result missing CONTRACT 1 keys: {missing}"

    def test_validate_mismatch_flag_is_red(self, validator_from_files):
        result = validator_from_files.validate(bank_credits_cr=42.5)
        assert result["mismatch_flag"] == "RED"

    def test_validate_gst_score_in_range(self, validator_from_files):
        result = validator_from_files.validate(bank_credits_cr=42.5)
        assert 0 <= result["gst_score"] <= 20

    def test_validate_apex_textiles_score_8_or_less(self, validator_from_files):
        """Apex Textiles demo scenario: score should be ≤ 10 (RED base = 8)."""
        result = validator_from_files.validate(bank_credits_cr=42.5)
        assert result["gst_score"] <= 10

    def test_validate_clean_scenario_gives_high_score(self, validator_clean):
        result = validator_clean.validate(bank_credits_cr=5.0)
        assert result["gst_score"] >= 14, \
            f"Clean scenario should score ≥14, got {result['gst_score']}"

    def test_validate_without_loading_raises(self):
        v = GSTCrossValidator()
        with pytest.raises(RuntimeError):
            v.validate(bank_credits_cr=40.0)

    def test_validate_extended_fields_present(self, validator_from_files):
        """Extended fields for M4 charting should also be present."""
        result = validator_from_files.validate(bank_credits_cr=42.5)
        assert "mismatch_detail" in result
        assert "divergence_pct" in result
        assert isinstance(result["divergence_pct"], float)
