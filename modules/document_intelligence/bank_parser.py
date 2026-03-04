"""
bank_parser.py — Module 1: Document Intelligence
==================================================
Parses bank statements (CSV or simple text PDF) into credit signals.

Output matches CONTRACT 1 bank_statement dict:
  {
      "avg_balance_cr":         1.80,
      "emi_outflow_monthly_cr": 0.42,
      "peak_balance_cr":        4.10,
      "regular_credits":        True,
      "month_on_month_volatility": 0.15,
      "stress_months_count":    2,
      "inward_outward_ratio_trend": [1.1, 0.9, 1.05]
  }

Supported formats:
  - CSV/Excel: SBI, HDFC, ICICI, Axis download formats
  - PDF: basic text-based bank statements (uses pdfplumber)

Usage:
    parser = BankStatementParser()
    result = parser.parse("bank_statement.csv")
"""

import re
import os
import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Transaction category keywords (case-insensitive)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_RULES = {
    "emi":      ["emi", "loan", "repayment", "installment", "instalment",
                 "lic", "home loan", "car loan", "term loan", "cc payment"],
    "salary":   ["salary", "sal/", "sal-", "payroll", "wage", "stipend",
                 "neft-sal", "imps-sal"],
    "supplier": ["purchase", "vendor", "supplier", "raw material", "material",
                 "goods", "stock", "inventory"],
    "customer": ["neft", "rtgs", "imps", "receipt", "payment recd",
                 "cr by", "credited by", "customer", "sale proceeds",
                 "collection"],
    "tax":      ["gst", "tds", "income tax", "advance tax", "tax payment",
                 "gst payment"],
    "utility":  ["electricity", "water", "gas", "broadband", "telephone",
                 "internet", "rent"],
}

# Standard column name aliases across Indian bank CSV exports
COLUMN_ALIASES = {
    "date":        ["date", "txn date", "transaction date", "value date",
                    "posting date", "tran date"],
    "description": ["description", "narration", "particulars", "details",
                    "transaction remarks", "remarks", "txn remarks"],
    "debit":       ["debit", "withdrawal", "dr", "debit amount", "withdrawal amt",
                    "amount (dr)", "debit(inr)"],
    "credit":      ["credit", "deposit", "cr", "credit amount", "deposit amt",
                    "amount (cr)", "credit(inr)"],
    "balance":     ["balance", "closing balance", "running balance",
                    "available balance", "bal", "balance (inr)"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renames columns to canonical names using alias lookup."""
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename_map = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and canonical not in rename_map.values():
                rename_map[alias] = canonical
                break
    return df.rename(columns=rename_map)


def _to_float(value) -> float:
    """Parses a cell value to float, handling commas and rupee symbols."""
    if pd.isna(value) or value == "":
        return 0.0
    cleaned = str(value).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _to_crore(value_in_rupees: float) -> float:
    """Converts raw rupees to crores."""
    return round(value_in_rupees / 10_000_000, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────────────────────

class BankStatementParser:
    """
    Parses Indian bank statements and extracts credit assessment signals.
    """

    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._is_crore_scale = False   # True if values in file are already in crores

    # ── Loaders ──────────────────────────────────────────────────────────────

    def load_statement(self, filepath: str) -> pd.DataFrame:
        """
        Loads a bank statement from CSV, Excel, or text-based PDF.

        Returns a normalized DataFrame with columns:
          date, description, debit, credit, balance
        """
        ext = os.path.splitext(filepath)[-1].lower()

        if ext in [".csv"]:
            df = self._load_csv(filepath)
        elif ext in [".xlsx", ".xls"]:
            df = self._load_excel(filepath)
        elif ext == ".pdf":
            df = self._load_pdf(filepath)
        else:
            raise ValueError(f"Unsupported bank statement format: {ext}")

        df = _normalize_columns(df)
        df = self._coerce_numeric(df)
        df = self._coerce_dates(df)

        # Auto-detect scale: if max balance is suspiciously small (< 100),
        # values are likely already in crores
        if "balance" in df.columns and df["balance"].max() < 1000:
            self._is_crore_scale = True

        self._df = df
        logger.info(f"Bank statement loaded: {len(df)} transactions from {filepath}")
        return df

    def load_from_dataframe(self, df: pd.DataFrame):
        """Loads directly from a pre-built DataFrame (for tests)."""
        self._df = df.copy()
        # Coerce numeric just in case
        self._df = self._coerce_numeric(self._df)

    def _load_csv(self, filepath: str) -> pd.DataFrame:
        """Tries multiple CSV encodings and skips header rows."""
        for encoding in ["utf-8", "latin1", "cp1252"]:
            try:
                df = pd.read_csv(filepath, dtype=str, encoding=encoding)
                # Skip leading rows that aren't the header (some banks add 3-4 info rows)
                df = self._find_real_header(df)
                return df
            except Exception:
                continue
        raise ValueError(f"Could not read CSV: {filepath}")

    def _load_excel(self, filepath: str) -> pd.DataFrame:
        df = pd.read_excel(filepath, dtype=str)
        return self._find_real_header(df)

    def _load_pdf(self, filepath: str) -> pd.DataFrame:
        """Extracts tabular data from a text-based bank statement PDF."""
        try:
            import pdfplumber
            rows = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        rows.extend(table)
            if rows:
                df = pd.DataFrame(rows[1:], columns=rows[0])  # first row = header
                return df
        except Exception as e:
            logger.error(f"PDF bank statement extraction failed: {e}")
        return pd.DataFrame()

    def _find_real_header(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Skips leading metadata rows (e.g. 'Account No: 12345...') to find
        the actual transaction table header.
        """
        date_col_keywords = ["date", "txn", "transaction", "value"]
        for i, row in df.iterrows():
            row_lower = " ".join(str(v).lower() for v in row.values)
            if any(kw in row_lower for kw in date_col_keywords):
                # This row looks like the header
                df.columns = [str(v).strip() for v in row.values]
                df = df.iloc[i + 1:].reset_index(drop=True)
                return df
        return df  # return as-is if no header row found

    def _coerce_numeric(self, df: pd.DataFrame) -> pd.DataFrame:
        """Converts debit, credit, balance columns to float."""
        for col in ["debit", "credit", "balance"]:
            if col in df.columns:
                df[col] = df[col].apply(_to_float)
        return df

    def _coerce_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tries to parse the date column."""
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        return df

    # ── Categorization ────────────────────────────────────────────────────────

    def categorize_transactions(self) -> pd.DataFrame:
        """
        Adds a 'category' column to the loaded DataFrame using keyword rules.

        Categories: emi | salary | supplier | customer | tax | utility | misc
        """
        if self._df is None:
            raise RuntimeError("Load a statement first with load_statement()")

        def classify(description: str) -> str:
            desc = str(description).lower()
            for category, keywords in CATEGORY_RULES.items():
                if any(kw in desc for kw in keywords):
                    return category
            return "misc"

        desc_col = "description" if "description" in self._df.columns else self._df.columns[1]
        self._df["category"] = self._df[desc_col].apply(classify)
        return self._df

    # ── Balance Statistics ────────────────────────────────────────────────────

    def compute_averages(self) -> dict:
        """
        Calculates average, peak, and minimum balance.

        Returns values in CRORE units.
        """
        if self._df is None or "balance" not in self._df.columns:
            return {"avg_balance_cr": 0.0, "peak_balance_cr": 0.0, "min_balance_cr": 0.0}

        balances = self._df["balance"].dropna()
        balances = balances[balances > 0]  # ignore zero/negative rows

        if balances.empty:
            return {"avg_balance_cr": 0.0, "peak_balance_cr": 0.0, "min_balance_cr": 0.0}

        if self._is_crore_scale:
            avg  = round(float(balances.mean()), 4)
            peak = round(float(balances.max()),  4)
            mini = round(float(balances.min()),  4)
        else:
            avg  = round(_to_crore(float(balances.mean())), 4)
            peak = round(_to_crore(float(balances.max())),  4)
            mini = round(_to_crore(float(balances.min())),  4)

        logger.info(f"Balance stats: avg={avg} Cr, peak={peak} Cr, min={mini} Cr")
        return {"avg_balance_cr": avg, "peak_balance_cr": peak, "min_balance_cr": mini}

    # ── EMI Detection ─────────────────────────────────────────────────────────

    def detect_emi_outflows(self) -> float:
        """
        Estimates average monthly EMI / loan repayment outflows.

        Strategy:
          - Filter debit transactions categorized as 'emi'
          - Group by month, sum debits
          - Return mean monthly EMI in crores

        Returns: float (crores per month)
        """
        if self._df is None:
            return 0.0

        df = self.categorize_transactions()
        emi_rows = df[df["category"] == "emi"]

        if emi_rows.empty or "debit" not in emi_rows.columns:
            logger.warning("No EMI transactions detected in statement")
            return 0.0

        if "date" in emi_rows.columns and emi_rows["date"].notna().any():
            emi_rows = emi_rows.copy()
            emi_rows["month"] = emi_rows["date"].dt.to_period("M")
            monthly = emi_rows.groupby("month")["debit"].sum()
            avg_monthly = float(monthly.mean())
        else:
            # No date column — simple average across all EMI debits
            n_months = max(len(df) // 30, 1)   # estimate months from row count
            avg_monthly = emi_rows["debit"].sum() / n_months

        result = avg_monthly if self._is_crore_scale else _to_crore(avg_monthly)
        logger.info(f"EMI outflow: ~{result:.4f} Cr/month")
        return round(result, 4)

    # ── Regular Credits Check ─────────────────────────────────────────────────

    def check_regular_credits(self, min_months_with_credits: int = 9) -> bool:
        """
        Returns True if the company received customer credits in at least
        `min_months_with_credits` out of 12 months (or out of available months).

        A company with consistent customer payments signals stable receivables.
        """
        if self._df is None or "credit" not in self._df.columns:
            return False

        df = self.categorize_transactions()
        customer_credits = df[(df["category"] == "customer") & (df["credit"] > 0)]

        if customer_credits.empty:
            # Fallback: any non-zero credit counts
            customer_credits = df[df["credit"] > 0]

        if customer_credits.empty:
            return False

        if "date" in customer_credits.columns and customer_credits["date"].notna().any():
            months_with_credits = customer_credits["date"].dt.to_period("M").nunique()
            total_months = df["date"].dt.to_period("M").nunique() if "date" in df.columns else 12
            # Adjust threshold proportionally if fewer than 12 months of data
            threshold = min(min_months_with_credits, max(1, int(total_months * 0.75)))
            result = months_with_credits >= threshold
        else:
            # No date info — assume True if there are any credits
            result = len(customer_credits) >= 3

        logger.info(f"Regular credits check: {result}")
        return bool(result)

    # ── Feature 6: Cash Flow Volatility ───────────────────────────────────────

    def analyze_cash_flow_volatility(self) -> dict:
        """
        Calculates Cash Flow Volatility metrics.
        Returns:
            {
                "month_on_month_volatility": float,
                "stress_months_count": int,
                "inward_outward_ratio_trend": list of floats
            }
        """
        default_res = {
            "month_on_month_volatility": 0.0,
            "stress_months_count": 0,
            "inward_outward_ratio_trend": []
        }
        if self._df is None or "date" not in self._df.columns or "debit" not in self._df.columns or "credit" not in self._df.columns:
            return default_res

        df = self._df.dropna(subset=["date"]).copy()
        if df.empty:
            return default_res

        df["month"] = df["date"].dt.to_period("M")
        
        monthly = df.groupby("month").agg({
            "credit": "sum",
            "debit": "sum"
        }).sort_index()

        if monthly.empty:
            return default_res

        # Inward/Outward ratio trend (last 6 months)
        # Handle zero division by setting it to 1.0 or just credit value
        monthly["ratio"] = np.where(monthly["debit"] > 0, monthly["credit"] / monthly["debit"], 1.0)
        inward_outward_ratio_trend = [round(float(x), 2) for x in monthly["ratio"].tolist()[-6:]]

        # Stress months (outflows > inflows)
        stress_months_count = int((monthly["credit"] < monthly["debit"]).sum())

        # MoM Volatility of inflows: std / mean (Coefficient of Variation)
        mean_cr = monthly["credit"].mean()
        std_cr = monthly["credit"].std(ddof=0)
        mom_vol = round(float(std_cr / mean_cr), 4) if mean_cr and mean_cr > 0 else 0.0

        res = {
            "month_on_month_volatility": mom_vol,
            "stress_months_count": stress_months_count,
            "inward_outward_ratio_trend": inward_outward_ratio_trend
        }
        logger.info(f"Cash flow volatility: {res}")
        return res

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def parse(self, filepath: str) -> dict:
        """
        Main entry point. Loads, parses, and extracts all bank signals.

        Args:
            filepath: Path to CSV, Excel, or PDF bank statement.

        Returns:
            bank_statement dict matching CONTRACT 1:
            {
                "avg_balance_cr":         float,
                "emi_outflow_monthly_cr": float,
                "peak_balance_cr":        float,
                "regular_credits":        bool,
            }
        """
        self.load_statement(filepath)

        averages = self.compute_averages()
        emi      = self.detect_emi_outflows()
        credits  = self.check_regular_credits()
        volatility = self.analyze_cash_flow_volatility()

        result = {
            "avg_balance_cr":         averages["avg_balance_cr"],
            "emi_outflow_monthly_cr": emi,
            "peak_balance_cr":        averages["peak_balance_cr"],
            "regular_credits":        credits,
            "month_on_month_volatility": volatility["month_on_month_volatility"],
            "stress_months_count":       volatility["stress_months_count"],
            "inward_outward_ratio_trend": volatility["inward_outward_ratio_trend"],
        }

        logger.info(f"Bank parse complete. Volatility: {volatility['month_on_month_volatility']}")
        return result
