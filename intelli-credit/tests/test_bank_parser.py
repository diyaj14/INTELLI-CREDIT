"""
tests/test_bank_parser.py
==========================
Tests for BankStatementParser.

Uses synthetic fixture CSV with known values:
  - 42 transactions over 5 months
  - Monthly EMI: 420,000 (fixed)  → ~0.042 Cr/month (in rupees)
  - Regular customer NEFT/RTGS credits every month → regular_credits = True
  - Balance trending ~3–6 Cr throughout

Run: pytest tests/test_bank_parser.py -v
"""
import os
import sys
import pytest
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.document_intelligence.bank_parser import (
    BankStatementParser,
    CATEGORY_RULES,
    _to_float,
    _to_crore,
    _normalize_columns,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
BANK_CSV = os.path.join(FIXTURES_DIR, "sample_bank_statement.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build minimal inline DataFrame (no file I/O)
# ─────────────────────────────────────────────────────────────────────────────

def make_statement_df(n_months=6) -> pd.DataFrame:
    """Creates a clean synthetic bank statement DataFrame."""
    rows = []
    base_date = datetime(2023, 4, 1)
    balance = 20_000_000  # 2 Cr starting

    for month in range(n_months):
        month_start = base_date + timedelta(days=30 * month)

        # Customer credit
        rows.append({
            "date":        month_start + timedelta(days=5),
            "description": "NEFT-Customer A Ltd",
            "debit":       0,
            "credit":      3_500_000,
            "balance":     balance + 3_500_000,
        })
        balance += 3_500_000

        # EMI
        rows.append({
            "date":        month_start + timedelta(days=10),
            "description": "EMI TERM LOAN SBI 45678",
            "debit":       420_000,
            "credit":      0,
            "balance":     balance - 420_000,
        })
        balance -= 420_000

        # Salary
        rows.append({
            "date":        month_start + timedelta(days=20),
            "description": "SALARY PAYROLL",
            "debit":       850_000,
            "credit":      0,
            "balance":     balance - 850_000,
        })
        balance -= 850_000

    return pd.DataFrame(rows)


@pytest.fixture
def parser_from_file():
    p = BankStatementParser()
    p.load_statement(BANK_CSV)
    return p


@pytest.fixture
def parser_inline():
    p = BankStatementParser()
    p.load_from_dataframe(make_statement_df(6))
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Tests: utility functions
# ─────────────────────────────────────────────────────────────────────────────

class TestUtilities:

    def test_to_float_basic(self):
        assert _to_float("1,23,45,000") == pytest.approx(12345000.0, rel=0.01)

    def test_to_float_with_rupee_symbol(self):
        assert _to_float("₹42,50,000") == pytest.approx(4250000.0, rel=0.01)

    def test_to_float_empty_returns_zero(self):
        assert _to_float("") == 0.0
        assert _to_float(None) == 0.0

    def test_to_crore_conversion(self):
        assert _to_crore(10_000_000) == pytest.approx(1.0, rel=0.01)
        assert _to_crore(42_500_000) == pytest.approx(4.25, rel=0.01)

    def test_normalize_columns_maps_aliases(self):
        df = pd.DataFrame(columns=["Txn Date", "Narration", "Withdrawal", "Deposit", "Running Balance"])
        df = _normalize_columns(df)
        assert "date"        in df.columns, f"Columns: {df.columns.tolist()}"
        assert "description" in df.columns
        assert "debit"       in df.columns
        assert "credit"      in df.columns
        assert "balance"     in df.columns


# ─────────────────────────────────────────────────────────────────────────────
# Tests: load_statement
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadStatement:

    def test_loads_csv_fixture(self):
        p = BankStatementParser()
        df = p.load_statement(BANK_CSV)
        assert df is not None
        assert len(df) > 0, "Should load at least some rows"

    def test_normalized_columns_present(self, parser_from_file):
        df = parser_from_file._df
        expected_cols = {"description", "debit", "credit", "balance"}
        present = expected_cols.intersection(df.columns)
        assert present, f"At least some canonical columns should be present, got {df.columns.tolist()}"

    def test_debit_credit_are_numeric(self, parser_from_file):
        df = parser_from_file._df
        if "debit" in df.columns:
            assert pd.api.types.is_numeric_dtype(df["debit"])
        if "credit" in df.columns:
            assert pd.api.types.is_numeric_dtype(df["credit"])

    def test_unsupported_format_raises(self):
        p = BankStatementParser()
        with pytest.raises(ValueError, match="Unsupported"):
            p.load_statement("/fake/path/file.txt")

    def test_load_from_dataframe(self, parser_inline):
        assert parser_inline._df is not None
        assert len(parser_inline._df) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: categorize_transactions
# ─────────────────────────────────────────────────────────────────────────────

class TestCategorizeTransactions:

    def test_adds_category_column(self, parser_inline):
        df = parser_inline.categorize_transactions()
        assert "category" in df.columns

    def test_emi_correctly_categorized(self, parser_inline):
        df = parser_inline.categorize_transactions()
        emi_rows = df[df["category"] == "emi"]
        assert len(emi_rows) > 0, "Should find EMI transactions"

    def test_customer_correctly_categorized(self, parser_inline):
        df = parser_inline.categorize_transactions()
        customer_rows = df[df["category"] == "customer"]
        assert len(customer_rows) > 0, "Should find customer credit transactions"

    def test_salary_correctly_categorized(self, parser_inline):
        df = parser_inline.categorize_transactions()
        salary_rows = df[df["category"] == "salary"]
        assert len(salary_rows) > 0, "Should find salary transactions"

    def test_all_categories_valid(self, parser_inline):
        valid_categories = set(CATEGORY_RULES.keys()) | {"misc"}
        df = parser_inline.categorize_transactions()
        unknown = set(df["category"].unique()) - valid_categories
        assert not unknown, f"Unknown categories found: {unknown}"

    def test_fixture_has_emi_transactions(self, parser_from_file):
        df = parser_from_file.categorize_transactions()
        emi_count = (df["category"] == "emi").sum()
        assert emi_count >= 3, f"Fixture should have multiple EMI rows, found {emi_count}"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: compute_averages
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeAverages:

    def test_returns_required_keys(self, parser_from_file):
        result = parser_from_file.compute_averages()
        assert "avg_balance_cr"  in result
        assert "peak_balance_cr" in result
        assert "min_balance_cr"  in result

    def test_avg_balance_is_positive(self, parser_from_file):
        result = parser_from_file.compute_averages()
        assert result["avg_balance_cr"] > 0, "Average balance should be positive"

    def test_peak_balance_gte_avg(self, parser_from_file):
        result = parser_from_file.compute_averages()
        assert result["peak_balance_cr"] >= result["avg_balance_cr"], \
            "Peak balance should be >= average balance"

    def test_fixture_avg_balance_reasonable(self, parser_from_file):
        """Fixture balances are ~2–6 Cr in rupees → expect avg ~2–7 Cr."""
        result = parser_from_file.compute_averages()
        assert 0.5 <= result["avg_balance_cr"] <= 20.0, \
            f"Avg balance {result['avg_balance_cr']} Cr seems outside expected range"

    def test_inline_avg_balance_reasonable(self, parser_inline):
        result = parser_inline.compute_averages()
        # Inline statement starts at 2 Cr, rises each month
        assert result["avg_balance_cr"] > 0

    def test_empty_balance_column_returns_zeros(self):
        p = BankStatementParser()
        p.load_from_dataframe(pd.DataFrame({
            "description": ["test"],
            "debit":       [0.0],
            "credit":      [0.0],
        }))
        result = p.compute_averages()
        assert result["avg_balance_cr"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_emi_outflows
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectEmiOutflows:

    def test_returns_float(self, parser_inline):
        result = parser_inline.detect_emi_outflows()
        assert isinstance(result, float)

    def test_emi_is_positive(self, parser_inline):
        result = parser_inline.detect_emi_outflows()
        assert result > 0, "Should detect positive EMI outflows from inline data"

    def test_emi_is_reasonable_range(self, parser_inline):
        """Inline data has fixed 420,000 Rs/month EMI → ~0.042 Cr/month."""
        result = parser_inline.detect_emi_outflows()
        # After conversion: 420000 Rs = 0.042 Cr
        assert 0.01 <= result <= 1.0, \
            f"EMI {result:.4f} Cr/month seems outside expected 0.01–1.0 range"

    def test_fixture_emi_detected(self, parser_from_file):
        result = parser_from_file.detect_emi_outflows()
        assert isinstance(result, float)
        assert result >= 0.0

    def test_no_emi_transactions_returns_zero(self):
        p = BankStatementParser()
        p.load_from_dataframe(pd.DataFrame({
            "description": ["NEFT Customer A", "SUPPLIER Payment", "Salary"],
            "debit":       [0.0, 500_000.0, 800_000.0],
            "credit":      [3_000_000.0, 0.0, 0.0],
            "balance":     [25_000_000.0, 24_500_000.0, 23_700_000.0],
        }))
        result = p.detect_emi_outflows()
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: check_regular_credits
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckRegularCredits:

    def test_returns_bool(self, parser_inline):
        result = parser_inline.check_regular_credits()
        assert isinstance(result, bool)

    def test_consistent_monthly_credits_returns_true(self, parser_inline):
        """6 months of consistent customer NEFT credits → True."""
        result = parser_inline.check_regular_credits()
        assert result is True

    def test_fixture_regular_credits(self, parser_from_file):
        result = parser_from_file.check_regular_credits()
        assert isinstance(result, bool)
        # Fixture has customer credits every month → expect True
        assert result is True

    def test_no_credits_returns_false(self):
        p = BankStatementParser()
        p.load_from_dataframe(pd.DataFrame({
            "description": ["EMI LOAN", "SALARY PAYROLL"],
            "debit":       [420_000, 850_000],
            "credit":      [0.0, 0.0],
            "balance":     [5_000_000, 4_150_000],
        }))
        result = p.check_regular_credits()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: parse() — full integration
# ─────────────────────────────────────────────────────────────────────────────

class TestParse:

    def test_parse_returns_contract1_keys(self):
        p = BankStatementParser()
        result = p.parse(BANK_CSV)
        required = {"avg_balance_cr", "emi_outflow_monthly_cr", "peak_balance_cr", "regular_credits",
                    "month_on_month_volatility", "stress_months_count", "inward_outward_ratio_trend"}
        missing = required - result.keys()
        assert not missing, f"Missing CONTRACT 1 keys: {missing}"

    def test_parse_all_values_correct_types(self):
        p = BankStatementParser()
        result = p.parse(BANK_CSV)
        assert isinstance(result["avg_balance_cr"],         float)
        assert isinstance(result["emi_outflow_monthly_cr"], float)
        assert isinstance(result["peak_balance_cr"],        float)
        assert isinstance(result["regular_credits"],        bool)
        assert isinstance(result["month_on_month_volatility"], float)
        assert isinstance(result["stress_months_count"],    int)
        assert isinstance(result["inward_outward_ratio_trend"], list)

    def test_parse_avg_balance_positive(self):
        p = BankStatementParser()
        result = p.parse(BANK_CSV)
        assert result["avg_balance_cr"] > 0

    def test_parse_regular_credits_true_for_fixture(self):
        p = BankStatementParser()
        result = p.parse(BANK_CSV)
        assert result["regular_credits"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: analyze_cash_flow_volatility (Feature 6)
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeCashFlowVolatility:

    def test_returns_required_keys(self, parser_inline):
        result = parser_inline.analyze_cash_flow_volatility()
        required = {"month_on_month_volatility", "stress_months_count", "inward_outward_ratio_trend"}
        missing = required - set(result.keys())
        assert not missing, f"Missing Volatility keys: {missing}"

    def test_inline_data_volatility(self, parser_inline):
        result = parser_inline.analyze_cash_flow_volatility()
        # Inline data has 3,500,000 credit every month (std=0, mean=3,500,000)
        assert result["month_on_month_volatility"] == 0.0
        # Inward 3.5M, Outward = 420K + 850K = 1.27M, so ratio is 3.5 / 1.27 = 2.76
        assert result["stress_months_count"] == 0
        assert all(r > 2.0 for r in result["inward_outward_ratio_trend"])

    def test_fixture_data_volatility(self, parser_from_file):
        result = parser_from_file.analyze_cash_flow_volatility()
        assert isinstance(result["month_on_month_volatility"], float)
        assert isinstance(result["stress_months_count"], int)
        assert isinstance(result["inward_outward_ratio_trend"], list)

    def test_empty_df_returns_defaults(self):
        p = BankStatementParser()
        p.load_from_dataframe(pd.DataFrame({"date": [], "debit": [], "credit": []}))
        result = p.analyze_cash_flow_volatility()
        assert result["month_on_month_volatility"] == 0.0
        assert result["stress_months_count"] == 0
        assert result["inward_outward_ratio_trend"] == []
