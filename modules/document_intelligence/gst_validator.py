"""
gst_validator.py — Module 1: Document Intelligence
====================================================
Detects GST fraud signals for Indian corporate credit assessment.

Three fraud detectors:
  1. GSTR-3B vs GSTR-2A mismatch  — ITC claimed > actually available = fraud
  2. Circular trading detection   — same GSTIN as both supplier & buyer
  3. Revenue inflation             — GST-declared sales vs actual bank credits

Output matches CONTRACT 1 gst_analysis dict:
  {
      "mismatch_pct":           18.2,
      "mismatch_flag":          "RED",
      "circular_trading_flag":  True,
      "revenue_inflation_flag": False,
      "gst_score":              8,       # out of 20
  }

Usage:
    validator = GSTCrossValidator()
    validator.load_gstr3b("gst_returns/gstr3b_FY24.xlsx")
    validator.load_gstr2a("gst_returns/gstr2a_FY24.xlsx")
    result = validator.validate(bank_credits_cr=42.5)
"""

import logging
import os
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring constants — tune these to align with M3 scoring weights
# ─────────────────────────────────────────────────────────────────────────────

GST_SCORE_MAP = {
    "GREEN":  20,   # mismatch < 5% — clean
    "YELLOW": 14,   # mismatch 5–10% — minor concern
    "RED":     8,   # mismatch > 10% — significant red flag
}

CIRCULAR_TRADING_DEDUCTION = 4   # additional points off if circular trading detected
REVENUE_INFLATION_DEDUCTION = 3  # additional points off if revenue inflation detected

# ─────────────────────────────────────────────────────────────────────────────
# Column name normalizer — Indian GST Excel exports vary in column naming
# ─────────────────────────────────────────────────────────────────────────────

GSTR3B_COLUMN_ALIASES = {
    "period":       ["period", "month", "tax period", "return period", "date", "filing month"],
    "taxable_value": ["taxable value", "taxable turnover", "taxable supply",
                      "total taxable", "gross sales", "value of supply"],
    "itc_claimed":  ["itc claimed", "input tax credit", "itc availed",
                     "total itc", "input credit claimed", "eligible itc"],
    "igst":         ["igst", "integrated gst", "igst claimed"],
    "cgst":         ["cgst", "central gst", "cgst claimed"],
    "sgst":         ["sgst", "state gst", "sgst claimed", "utgst"],
}

GSTR2A_COLUMN_ALIASES = {
    "period":           ["period", "month", "tax period", "invoice month", "date"],
    "supplier_gstin":   ["supplier gstin", "gstin of supplier", "supplier gst",
                         "counterparty gstin", "vendor gstin", "from gstin"],
    "itc_available":    ["itc available", "eligible itc", "credit available",
                         "input tax", "itc", "credit amount", "net itc"],
    "invoice_value":    ["invoice value", "total invoice", "taxable value",
                         "gross amount", "supply value"],
}


def _normalize_column(df: pd.DataFrame, aliases: dict) -> pd.DataFrame:
    """
    Renames DataFrame columns to canonical names using the alias map.
    Case-insensitive and strips whitespace.
    """
    rename_map = {}
    df.columns = [str(c).strip().lower() for c in df.columns]

    for canonical, variants in aliases.items():
        for variant in variants:
            if variant.lower() in df.columns:
                rename_map[variant.lower()] = canonical
                break

    return df.rename(columns=rename_map)


def _read_file(filepath: str) -> pd.DataFrame:
    """Reads CSV or Excel file into a DataFrame."""
    ext = os.path.splitext(filepath)[-1].lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(filepath, dtype=str)
    elif ext == ".csv":
        return pd.read_csv(filepath, dtype=str)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .xlsx, .xls, or .csv")


# ─────────────────────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────────────────────

class GSTCrossValidator:
    """
    Performs GST intelligence analysis for credit appraisal.

    Three independent fraud signal detectors plus a composite scoring engine.
    Designed for Indian GSTR-3B and GSTR-2A Excel export formats.
    """

    def __init__(self):
        self.gstr3b: Optional[pd.DataFrame] = None
        self.gstr2a: Optional[pd.DataFrame] = None
        self._mismatch_detail: dict = {}   # quarter-wise breakdown for charting

    # ── Data Loaders ──────────────────────────────────────────────────────────

    def load_gstr3b(self, filepath: str) -> pd.DataFrame:
        """
        Loads GSTR-3B (self-declared monthly summary return).
        Expected columns: period, taxable_value, itc_claimed (any alias).

        Returns the normalized DataFrame.
        """
        df = _read_file(filepath)
        df = _normalize_column(df, GSTR3B_COLUMN_ALIASES)

        # Ensure required columns exist
        for col in ["period", "itc_claimed"]:
            if col not in df.columns:
                raise ValueError(
                    f"GSTR-3B file missing required column: '{col}'. "
                    f"Found columns: {list(df.columns)}. "
                    f"Rename or add this column."
                )

        # Parse numeric columns
        for col in ["taxable_value", "itc_claimed", "igst", "cgst", "sgst"]:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").str.strip(),
                    errors="coerce"
                ).fillna(0.0)

        self.gstr3b = df
        logger.info(f"GSTR-3B loaded: {len(df)} periods from {filepath}")
        return df

    def load_gstr2a(self, filepath: str) -> pd.DataFrame:
        """
        Loads GSTR-2A (auto-populated credit from supplier GSTR-1 filings).
        Expected columns: period, supplier_gstin, itc_available (any alias).

        Returns the normalized DataFrame.
        """
        df = _read_file(filepath)
        df = _normalize_column(df, GSTR2A_COLUMN_ALIASES)

        for col in ["period", "itc_available"]:
            if col not in df.columns:
                raise ValueError(
                    f"GSTR-2A file missing required column: '{col}'. "
                    f"Found columns: {list(df.columns)}."
                )

        for col in ["itc_available", "invoice_value"]:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").str.strip(),
                    errors="coerce"
                ).fillna(0.0)

        self.gstr2a = df
        logger.info(f"GSTR-2A loaded: {len(df)} records from {filepath}")
        return df

    def load_from_dataframes(self, gstr3b_df: pd.DataFrame, gstr2a_df: pd.DataFrame):
        """
        Alternative loader: use pre-built DataFrames directly (useful in tests).
        Column names must already be canonical (period, itc_claimed, itc_available, etc.)
        """
        self.gstr3b = gstr3b_df.copy()
        self.gstr2a = gstr2a_df.copy()

    # ── Detector 1: ITC Mismatch (GSTR-3B vs GSTR-2A) ────────────────────────

    def compute_mismatch_pct(self) -> tuple[float, dict]:
        """
        Computes the overall ITC mismatch percentage:
            mismatch% = (ITC claimed in 3B − ITC available in 2A) / ITC available in 2A × 100

        A positive mismatch means the company claimed more ITC than its
        suppliers reported → potential ITC fraud or genuine timing difference.

        Returns:
            (overall_mismatch_pct, period_wise_detail)
        """
        if self.gstr3b is None or self.gstr2a is None:
            raise RuntimeError("Load GSTR-3B and GSTR-2A first using load_gstr3b() / load_gstr2a()")

        # Aggregate GSTR-2A by period (may have multiple suppliers per period)
        gstr2a_by_period = (
            self.gstr2a
            .groupby("period", as_index=False)["itc_available"]
            .sum()
            .rename(columns={"itc_available": "itc_available_2a"})
        )

        # GSTR-3B is already one row per period
        gstr3b_cols = ["period", "itc_claimed"]
        gstr3b_by_period = self.gstr3b[gstr3b_cols].copy()

        # Merge on period
        merged = pd.merge(gstr3b_by_period, gstr2a_by_period, on="period", how="outer").fillna(0)

        if merged.empty:
            logger.warning("No matching periods between GSTR-3B and GSTR-2A")
            return 0.0, {}

        # Compute per-period mismatch
        merged["mismatch_abs"] = merged["itc_claimed"] - merged["itc_available_2a"]
        merged["mismatch_pct"] = np.where(
            merged["itc_available_2a"] > 0,
            (merged["mismatch_abs"] / merged["itc_available_2a"]) * 100,
            0.0
        )

        # Overall: sum of claimed vs sum of available
        total_claimed = merged["itc_claimed"].sum()
        total_available = merged["itc_available_2a"].sum()

        if total_available == 0:
            logger.warning("Total ITC available (2A) is zero — cannot compute mismatch")
            return 0.0, {}

        overall_mismatch = round(
            ((total_claimed - total_available) / total_available) * 100, 2
        )
        # Cap at 0 (negative mismatch = under-claimed, not a fraud signal)
        overall_mismatch = max(0.0, overall_mismatch)

        # Store period-wise detail for charting in M4
        self._mismatch_detail = merged.set_index("period")[
            ["itc_claimed", "itc_available_2a", "mismatch_pct"]
        ].to_dict(orient="index")

        logger.info(f"ITC mismatch: {overall_mismatch:.1f}% "
                    f"(Claimed: {total_claimed:.2f}, Available: {total_available:.2f})")

        return overall_mismatch, self._mismatch_detail

    # ── Detector 2: Circular Trading ─────────────────────────────────────────
    def detect_circular_trading(self, my_gstin: str = "TARGET") -> tuple[bool, list, dict]:
        """
        Detects circular trading and generates graph-ready data (nodes/edges).

        Returns:
            (is_circular: bool, flagged_gstins: list, graph_data: dict)
        """
        graph_data = {
            "nodes": [{"id": my_gstin, "label": "Target Company", "type": "main"}],
            "edges": []
        }
        
        if self.gstr2a is None:
            return False, [], graph_data

        # 1. Map Purchases (from GSTR-2A)
        # Aggregating by supplier
        purchases = (
            self.gstr2a.groupby("supplier_gstin")["itc_available"]
            .sum()
            .to_dict()
        )
        
        supplier_gstins = set()
        for gstin, amt in purchases.items():
            u_gstin = str(gstin).strip().upper()
            supplier_gstins.add(u_gstin)
            graph_data["nodes"].append({"id": u_gstin, "label": f"Supplier {u_gstin[-4:]}", "type": "supplier"})
            graph_data["edges"].append({
                "from": u_gstin, 
                "to": my_gstin, 
                "value": round(amt, 2), 
                "type": "purchase"
            })

        # 2. Map Sales (if buyer_gstin exists in GSTR-3B or similar)
        buyer_gstins = set()
        # Look for possible buyer columns
        buyer_cols = [c for c in (self.gstr3b.columns if self.gstr3b is not None else [])
                      if "buyer" in c.lower() or "customer" in c.lower() or "gstin" in c.lower() 
                      and c != "supplier_gstin"]
        
        if buyer_cols:
            sales = (
                self.gstr3b.groupby(buyer_cols[0])["taxable_value"]
                .sum()
                .to_dict()
            )
            for gstin, amt in sales.items():
                u_gstin = str(gstin).strip().upper()
                buyer_gstins.add(u_gstin)
                # Avoid duplicate nodes
                if u_gstin not in supplier_gstins:
                    graph_data["nodes"].append({"id": u_gstin, "label": f"Buyer {u_gstin[-4:]}", "type": "buyer"})
                else:
                    # Circular Node!
                    for node in graph_data["nodes"]:
                        if node["id"] == u_gstin:
                            node["type"] = "circular"
                
                graph_data["edges"].append({
                    "from": my_gstin, 
                    "to": u_gstin, 
                    "value": round(amt, 2), 
                    "type": "sale"
                })

        overlap = supplier_gstins.intersection(buyer_gstins)
        overlap_ratio = len(overlap) / max(len(supplier_gstins), 1)
        is_circular = overlap_ratio > 0.30 or len(overlap) >= 1
        
        return bool(is_circular), list(overlap), graph_data

    # ── Detector 3: Revenue Inflation ─────────────────────────────────────────

    def detect_revenue_inflation(self, bank_credits_cr: float) -> tuple[bool, float]:
        """
        Compares GST-declared sales turnover (GSTR-3B) vs actual bank credits.

        If a company declares ₹100 Cr in sales but bank shows only ₹75 Cr in
        credits, the ₹25 Cr difference is suspicious — possible revenue inflation.

        Args:
            bank_credits_cr: Total annual bank credits (from BankStatementParser)

        Returns:
            (is_inflated: bool, divergence_pct: float)
        """
        if self.gstr3b is None:
            return False, 0.0

        if "taxable_value" not in self.gstr3b.columns:
            logger.warning("No taxable_value column in GSTR-3B — revenue inflation check skipped")
            return False, 0.0

        # Sum up annual taxable turnover from GSTR-3B (convert to crores)
        total_gst_sales = self.gstr3b["taxable_value"].sum()

        # If values look like they're in rupees (> 10M), convert to crores
        if total_gst_sales > 10_000_000:
            total_gst_sales = total_gst_sales / 10_000_000

        if total_gst_sales <= 0:
            return False, 0.0

        if bank_credits_cr <= 0:
            return False, 0.0

        # Divergence: how much is GST sales HIGHER than bank credits (%)
        divergence_pct = ((total_gst_sales - bank_credits_cr) / bank_credits_cr) * 100

        # Allow up to 15% divergence (could be credit sales, delayed realisation, etc.)
        is_inflated = divergence_pct > 15.0

        logger.info(
            f"Revenue inflation check: GST sales={total_gst_sales:.2f} Cr, "
            f"Bank credits={bank_credits_cr:.2f} Cr, "
            f"Divergence={divergence_pct:.1f}% — inflated={is_inflated}"
        )
        return bool(is_inflated), round(float(divergence_pct), 2)

    # ── Classification & Scoring ──────────────────────────────────────────────

    def classify_flag(self, mismatch_pct: float) -> str:
        """
        Classifies ITC mismatch into traffic-light flag.

        GREEN  < 5%   — normal timing differences, acceptable
        YELLOW 5–10%  — needs monitoring, qualitative explanation needed
        RED    > 10%  — significant discrepancy, potential ITC fraud
        """
        if mismatch_pct < 5.0:
            return "GREEN"
        elif mismatch_pct <= 10.0:
            return "YELLOW"
        else:
            return "RED"

    def gst_score(
        self,
        flag: str,
        circular_trading: bool,
        revenue_inflation: bool,
    ) -> int:
        """
        Calculates GST compliance score out of 20.

        Base:
          GREEN  → 20
          YELLOW → 14
          RED    →  8

        Deductions:
          Circular trading detected → −4
          Revenue inflation detected → −3

        Minimum score: 0
        """
        base = GST_SCORE_MAP.get(flag, 8)
        deductions = 0

        if circular_trading:
            deductions += CIRCULAR_TRADING_DEDUCTION
        if revenue_inflation:
            deductions += REVENUE_INFLATION_DEDUCTION

        score = max(0, base - deductions)
        logger.info(
            f"GST score: base={base} - deductions={deductions} = {score}/20 "
            f"(flag={flag}, circular={circular_trading}, revenue_inflation={revenue_inflation})"
        )
        return score

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def validate(
        self,
        bank_credits_cr: float = 0.0,
        gstr3b_path: Optional[str] = None,
        gstr2a_path: Optional[str] = None,
        my_gstin: str = "TARGET_COMPANY"
    ) -> dict:
        """
        Runs the full GST validation pipeline.

        Args:
            bank_credits_cr: Annual bank statement total credits (for revenue inflation check).
            gstr3b_path:     Path to GSTR-3B file (if not already loaded via load_gstr3b()).
            gstr2a_path:     Path to GSTR-2A file (if not already loaded via load_gstr2a()).
            my_gstin:        The GSTIN of the company being assessed.

        Returns:
            gst_analysis dict matching CONTRACT 1:
            {
                "mismatch_pct":           float,
                "mismatch_flag":          "RED" | "YELLOW" | "GREEN",
                "circular_trading_flag":  bool,
                "revenue_inflation_flag": bool,
                "gst_score":              int (0–20),
                "mismatch_detail":        dict (period-wise, for charting),
                "circular_trading_gstins": list,
                "divergence_pct":         float,
            }
        """
        # Load files if paths provided
        if gstr3b_path:
            self.load_gstr3b(gstr3b_path)
        if gstr2a_path:
            self.load_gstr2a(gstr2a_path)

        if self.gstr3b is None or self.gstr2a is None:
            raise RuntimeError(
                "GSTR-3B and GSTR-2A must be loaded before calling validate(). "
                "Use load_gstr3b() / load_gstr2a() or pass file paths to validate()."
            )

        logger.info("Running GST cross-validation...")

        # ── Run all three detectors ────────────────────────────────────────────
        mismatch_pct, mismatch_detail = self.compute_mismatch_pct()
        is_circular, flagged_gstins, graph_data = self.detect_circular_trading(my_gstin)
        is_inflated, divergence_pct   = self.detect_revenue_inflation(bank_credits_cr)

        # ── Classify and score ─────────────────────────────────────────────────
        flag  = self.classify_flag(mismatch_pct)
        score = self.gst_score(flag, is_circular, is_inflated)

        result = {
            # CONTRACT 1 required fields
            "mismatch_pct":           mismatch_pct,
            "mismatch_flag":          flag,
            "circular_trading_flag":  is_circular,
            "revenue_inflation_flag": is_inflated,
            "gst_score":              score,

            # Extended fields (for M4 charting and M3 explainability)
            "mismatch_detail":         mismatch_detail,
            "circular_trading_gstins": flagged_gstins,
            "circular_graph_data":     graph_data,
            "divergence_pct":          divergence_pct,
        }

        logger.info(
            f"GST validation complete — "
            f"mismatch={mismatch_pct:.1f}% ({flag}), "
            f"circular={is_circular}, inflation={is_inflated}, "
            f"score={score}/20"
        )
        return result
