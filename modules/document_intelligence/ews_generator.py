"""
ews_generator.py — Module 1: Document Intelligence
====================================================
Early Warning Signal (EWS) Generator following the RBI framework for
identifying credit stress before accounts become NPAs.

Input: financials dict + gst_analysis dict + bank_statement dict + trend_signals list
Output: early_warning_signals list  (added to CONTRACT 1)

Signal format:
  {
    "level":    1 | 2 | 3,
    "signal":   str,       # human-readable description
    "category": str,       # "liquidity" | "leverage" | "profitability" |
                           #  "fraud_risk" | "gst_compliance" | "banking_behaviour" |
                           #  "revenue_trend" | "debt_serviceability"
    "field":    str,       # which metric triggered this (for frontend highlight)
    "threshold":str,       # the RBI/internal threshold that was breached
  }

RBI EWS Levels:
  Level 1 — Watch:          Early deterioration — monitor closely
  Level 2 — Special Mention: Significant deterioration — proactive action needed
  Level 3 — Stress:         Severe distress — near NPA territory

Usage:
    gen = EarlyWarningSignalGenerator(
        financials, gst_analysis, bank_statement, trend_signals
    )
    signals = gen.generate()
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RBI-aligned thresholds (configurable)
# ─────────────────────────────────────────────────────────────────────────────

THRESHOLDS = {
    # Debt Serviceability
    "dscr_stress":   1.0,    # Level 3 if below this
    "dscr_caution":  1.25,   # Level 2 if below this
    "dscr_watch":    1.5,    # Level 1 if below this

    # Liquidity
    "current_ratio_stress":  1.0,    # Level 2 if below
    "current_ratio_caution": 1.33,   # Level 1 if below (RBI norm)

    # Leverage
    "de_stress":   3.0,   # Level 2 if above
    "de_caution":  2.0,   # Level 1 if above

    # Profitability
    "interest_coverage_stress":  1.5,   # Level 2 if below
    "interest_coverage_caution": 2.5,   # Level 1 if below

    # GST compliance
    "gst_mismatch_stress":   15.0,   # Level 2 if above (%)
    "gst_mismatch_caution":   5.0,   # Level 1 if above (%)

    # Banking behaviour
    "emi_to_balance_ratio":   0.5,   # Level 1 if EMI > 50% of avg balance
    "emi_to_balance_stress":  1.0,   # Level 2 if EMI >= avg balance
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────────────────────

class EarlyWarningSignalGenerator:
    """
    Generates RBI EWS-aligned early warning signals from MODULE 1 outputs.

    Covers 6 categories:
      1. Debt serviceability (DSCR)
      2. Liquidity (current ratio)
      3. Leverage (debt-to-equity)
      4. Profitability (net profit, interest coverage)
      5. GST compliance (mismatch %, circular trading, revenue inflation)
      6. Banking behaviour (EMI vs balance, irregular inflows)
    """

    def __init__(
        self,
        financials:      Dict[str, Any],
        gst_analysis:    Dict[str, Any],
        bank_statement:  Dict[str, Any],
        trend_signals:   Optional[List[Dict[str, Any]]] = None,
    ):
        self.fin  = financials    or {}
        self.gst  = gst_analysis  or {}
        self.bank = bank_statement or {}
        self.trend_signals = trend_signals or []
        self._signals: List[Dict[str, Any]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self) -> List[Dict[str, Any]]:
        """
        Runs all EWS rule checks and returns the complete early_warning_signals list,
        deduplicated and sorted by level (highest severity first).
        """
        self._signals = []

        self._check_dscr()
        self._check_current_ratio()
        self._check_leverage()
        self._check_profitability()
        self._check_interest_coverage()
        self._check_gst_compliance()
        self._check_banking_behaviour()
        self._merge_trend_signals()

        # Deduplicate (same level + field = skip)
        seen = set()
        unique_signals = []
        for s in self._signals:
            key = (s["level"], s["field"])
            if key not in seen:
                seen.add(key)
                unique_signals.append(s)

        # Sort: Level 3 first, then 2, then 1
        unique_signals.sort(key=lambda s: -s["level"])

        logger.info(
            f"EWS generation complete: {len(unique_signals)} signals "
            f"(L1={sum(1 for s in unique_signals if s['level']==1)}, "
            f"L2={sum(1 for s in unique_signals if s['level']==2)}, "
            f"L3={sum(1 for s in unique_signals if s['level']==3)})"
        )
        return unique_signals

    # ── Rule Checks ───────────────────────────────────────────────────────────

    def _check_dscr(self) -> None:
        """DSCR (Debt Service Coverage Ratio) — RBI #1 credit stress indicator."""
        dscr = self.fin.get("dscr")
        if dscr is None:
            return

        if dscr < THRESHOLDS["dscr_stress"]:
            self._add(
                level=2,
                signal=(
                    f"DSCR {dscr:.2f} below 1.0 — operating income cannot cover "
                    f"debt service obligations (RBI threshold: {THRESHOLDS['dscr_caution']})"
                ),
                category="debt_serviceability",
                field="dscr",
                threshold=f"< {THRESHOLDS['dscr_stress']}",
            )
        elif dscr < THRESHOLDS["dscr_caution"]:
            self._add(
                level=1,
                signal=(
                    f"DSCR {dscr:.2f} below RBI recommended minimum of "
                    f"{THRESHOLDS['dscr_caution']}"
                ),
                category="debt_serviceability",
                field="dscr",
                threshold=f"< {THRESHOLDS['dscr_caution']}",
            )
        elif dscr < THRESHOLDS["dscr_watch"]:
            self._add(
                level=1,
                signal=(
                    f"DSCR {dscr:.2f} below preferred threshold of "
                    f"{THRESHOLDS['dscr_watch']} — monitor debt serviceability"
                ),
                category="debt_serviceability",
                field="dscr",
                threshold=f"< {THRESHOLDS['dscr_watch']}",
            )

    def _check_current_ratio(self) -> None:
        """Current Ratio — short-term liquidity stress indicator."""
        cr = self.fin.get("current_ratio")
        if cr is None:
            return

        if cr < THRESHOLDS["current_ratio_stress"]:
            self._add(
                level=2,
                signal=(
                    f"Current ratio {cr:.2f} below 1.0 — current liabilities exceed "
                    f"current assets (severe short-term liquidity risk)"
                ),
                category="liquidity",
                field="current_ratio",
                threshold=f"< {THRESHOLDS['current_ratio_stress']}",
            )
        elif cr < THRESHOLDS["current_ratio_caution"]:
            self._add(
                level=1,
                signal=(
                    f"Current ratio {cr:.2f} below RBI norm of "
                    f"{THRESHOLDS['current_ratio_caution']} — liquidity under pressure"
                ),
                category="liquidity",
                field="current_ratio",
                threshold=f"< {THRESHOLDS['current_ratio_caution']}",
            )

    def _check_leverage(self) -> None:
        """Debt-to-Equity — over-leverage indicator."""
        de = self.fin.get("debt_to_equity")
        if de is None:
            return

        if de > THRESHOLDS["de_stress"]:
            self._add(
                level=2,
                signal=(
                    f"Debt-to-Equity {de:.2f}x — dangerously over-leveraged "
                    f"(internal limit: {THRESHOLDS['de_stress']}x)"
                ),
                category="leverage",
                field="debt_to_equity",
                threshold=f"> {THRESHOLDS['de_stress']}",
            )
        elif de > THRESHOLDS["de_caution"]:
            self._add(
                level=1,
                signal=(
                    f"Debt-to-Equity {de:.2f}x above recommended maximum of "
                    f"{THRESHOLDS['de_caution']}x"
                ),
                category="leverage",
                field="debt_to_equity",
                threshold=f"> {THRESHOLDS['de_caution']}",
            )

    def _check_profitability(self) -> None:
        """Net profit — loss-making entity detection."""
        np_val = self.fin.get("net_profit_cr")
        rev    = self.fin.get("revenue_cr", 0) or 1  # avoid div-by-zero

        if np_val is None:
            return

        if np_val < 0:
            self._add(
                level=3,
                signal=(
                    f"Net loss of ₹{abs(np_val):.2f} Cr — company is loss-making. "
                    f"Repayment capacity severely impaired."
                ),
                category="profitability",
                field="net_profit_cr",
                threshold="< 0",
            )
        elif np_val == 0:
            self._add(
                level=2,
                signal="Net profit is zero — no retained earnings to service future debt",
                category="profitability",
                field="net_profit_cr",
                threshold="= 0",
            )
        else:
            # Net profit margin check
            npm = (np_val / rev) * 100
            if npm < 2.0:
                self._add(
                    level=1,
                    signal=(
                        f"Net profit margin {npm:.1f}% — very thin margin "
                        f"(< 2% signals fragile profitability)"
                    ),
                    category="profitability",
                    field="net_profit_cr",
                    threshold="margin < 2%",
                )

    def _check_interest_coverage(self) -> None:
        """Interest Coverage Ratio — ability to meet interest obligations."""
        icr = self.fin.get("interest_coverage")
        if icr is None:
            return

        if icr < THRESHOLDS["interest_coverage_stress"]:
            self._add(
                level=2,
                signal=(
                    f"Interest Coverage Ratio {icr:.2f}x below "
                    f"{THRESHOLDS['interest_coverage_stress']}x — "
                    f"operating income barely covers interest payments"
                ),
                category="debt_serviceability",
                field="interest_coverage",
                threshold=f"< {THRESHOLDS['interest_coverage_stress']}",
            )
        elif icr < THRESHOLDS["interest_coverage_caution"]:
            self._add(
                level=1,
                signal=(
                    f"Interest Coverage Ratio {icr:.2f}x below preferred minimum "
                    f"of {THRESHOLDS['interest_coverage_caution']}x"
                ),
                category="debt_serviceability",
                field="interest_coverage",
                threshold=f"< {THRESHOLDS['interest_coverage_caution']}",
            )

    def _check_gst_compliance(self) -> None:
        """GST fraud signals — ITC mismatch, circular trading, revenue inflation."""
        mismatch_pct = self.gst.get("mismatch_pct", 0) or 0
        circular     = self.gst.get("circular_trading_flag", False)
        inflation    = self.gst.get("revenue_inflation_flag", False)
        gst_score    = self.gst.get("gst_score", 20)

        # ITC Mismatch
        if mismatch_pct > THRESHOLDS["gst_mismatch_stress"]:
            self._add(
                level=2,
                signal=(
                    f"GST ITC mismatch {mismatch_pct:.1f}% — exceeds {THRESHOLDS['gst_mismatch_stress']}% "
                    f"threshold, indicating potential input tax credit fraud"
                ),
                category="gst_compliance",
                field="gst_mismatch_pct",
                threshold=f"> {THRESHOLDS['gst_mismatch_stress']}%",
            )
        elif mismatch_pct > THRESHOLDS["gst_mismatch_caution"]:
            self._add(
                level=1,
                signal=(
                    f"GST ITC mismatch {mismatch_pct:.1f}% — above {THRESHOLDS['gst_mismatch_caution']}% "
                    f"caution threshold"
                ),
                category="gst_compliance",
                field="gst_mismatch_pct",
                threshold=f"> {THRESHOLDS['gst_mismatch_caution']}%",
            )

        # Circular Trading
        if circular:
            self._add(
                level=2,
                signal=(
                    "Circular trading pattern detected in GST data — "
                    "artificial revenue inflation through related-party transactions"
                ),
                category="fraud_risk",
                field="circular_trading_flag",
                threshold="circular_trading = True",
            )

        # Revenue Inflation
        if inflation:
            self._add(
                level=2,
                signal=(
                    "Revenue inflation detected — GST-reported revenue significantly "
                    "exceeds P&L revenue, suggesting window dressing"
                ),
                category="fraud_risk",
                field="revenue_inflation_flag",
                threshold="revenue_inflation = True",
            )

        # Low GST composite score
        if gst_score is not None and gst_score < 10:
            self._add(
                level=2,
                signal=(
                    f"GST composite score {gst_score}/20 — multiple GST compliance "
                    f"failures detected"
                ),
                category="gst_compliance",
                field="gst_score",
                threshold="< 10/20",
            )
        elif gst_score is not None and gst_score < 15:
            self._add(
                level=1,
                signal=(
                    f"GST composite score {gst_score}/20 — moderate compliance gaps"
                ),
                category="gst_compliance",
                field="gst_score",
                threshold="< 15/20",
            )

    def _check_banking_behaviour(self) -> None:
        """Bank statement signals — EMI burden, irregular credits."""
        avg_bal = self.bank.get("avg_balance_cr", 0) or 0
        emi     = self.bank.get("emi_outflow_monthly_cr", 0) or 0
        credits = self.bank.get("regular_credits", True)

        # EMI-to-balance stress
        if avg_bal > 0 and emi > 0:
            ratio = emi / avg_bal
            if ratio >= THRESHOLDS["emi_to_balance_stress"]:
                self._add(
                    level=2,
                    signal=(
                        f"Monthly EMI ₹{emi:.2f} Cr ≥ avg balance ₹{avg_bal:.2f} Cr "
                        f"— severe cash squeeze, high default risk"
                    ),
                    category="banking_behaviour",
                    field="emi_outflow_monthly_cr",
                    threshold="EMI ≥ avg_balance",
                )
            elif ratio >= THRESHOLDS["emi_to_balance_ratio"]:
                self._add(
                    level=1,
                    signal=(
                        f"Monthly EMI ₹{emi:.2f} Cr is {ratio*100:.0f}% of avg balance "
                        f"₹{avg_bal:.2f} Cr — limited liquidity buffer"
                    ),
                    category="banking_behaviour",
                    field="emi_outflow_monthly_cr",
                    threshold="EMI > 50% of avg_balance",
                )

        # Irregular customer credits
        if not credits:
            self._add(
                level=1,
                signal=(
                    "Irregular customer credit inflows — receipts not consistent "
                    "across months, signalling unstable receivables"
                ),
                category="banking_behaviour",
                field="regular_credits",
                threshold="regular_credits = False",
            )

    def _merge_trend_signals(self) -> None:
        """
        Incorporates trend_signals from FinancialExtractor (Feature 1) to avoid
        duplicating the trend analysis logic. Filters to avoid duplicate entries.
        """
        existing_fields_levels = {(s["level"], s["field"]) for s in self._signals}

        for ts in self.trend_signals:
            key = (ts["level"], ts.get("field", ""))
            if key not in existing_fields_levels:
                # Add threshold field if missing (trend signals don't have it)
                enriched = dict(ts)
                enriched.setdefault("threshold", "trend-based")
                self._signals.append(enriched)
                existing_fields_levels.add(key)

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _add(
        self,
        level: int,
        signal: str,
        category: str,
        field: str,
        threshold: str = "",
    ) -> None:
        """Appends a signal dict to the internal signals list."""
        self._signals.append({
            "level":     level,
            "signal":    signal,
            "category":  category,
            "field":     field,
            "threshold": threshold,
        })
        logger.debug(f"[EWS L{level}] {category}/{field}: {signal[:60]}...")
