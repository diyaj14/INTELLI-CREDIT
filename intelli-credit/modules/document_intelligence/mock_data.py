"""
mock_data.py — Module 1: Document Intelligence
===============================================
Hardcoded DocumentReport for demo company: Apex Textiles Pvt Ltd
This is the CONTRACT 1 output that M3 (Scoring) and M4 (Frontend) can use
immediately, even before the real pipeline is built.

Usage:
    from modules.document_intelligence.mock_data import APEX_TEXTILES_DOC_REPORT
    from modules.document_intelligence.mock_data import HEALTHY_COMPANY_DOC_REPORT
"""

# ---------------------------------------------------------------------------
# DEMO SCENARIO 1: Apex Textiles Pvt Ltd
# Decision will be: LEND WITH CONDITIONS (score ~54/100)
# Key signals: DSCR below threshold, high GST mismatch, litigation found
# ---------------------------------------------------------------------------

APEX_TEXTILES_DOC_REPORT = {
    "company_name": "Apex Textiles Pvt Ltd",
    "gstin": "27AAPCA1234F1Z5",

    # ── Financial Metrics (extracted from Annual Report PDF, FY2024) ──────
    "financials": {
        "revenue_cr":           42.5,   # ₹ Crore
        "ebitda_cr":             6.1,
        "net_profit_cr":         2.3,
        "total_assets_cr":      38.0,
        "total_liabilities_cr": 24.0,
        "net_worth_cr":         14.0,
        "dscr":                  0.89,  # Below RBI threshold of 1.25 ← RED FLAG
        "current_ratio":         1.10,  # Below ideal of 1.33
        "debt_to_equity":        1.71,  # Within acceptable range (<2)
        "interest_coverage":     2.40,  # Below ideal of 3.0
    },

    # ── GST Cross-Validation (GSTR-3B vs GSTR-2A, last 4 quarters) ───────
    "gst_analysis": {
        "mismatch_pct":            18.2,   # ITC claimed > ITC available by 18.2%
        "mismatch_flag":           "RED",  # >10% → RED
        "circular_trading_flag":   True,   # Same GSTIN appears as supplier + buyer
        "revenue_inflation_flag":  False,
        "gst_score":               8,      # out of 20
        "mismatch_detail": {
            "Q1-FY24": {"itc_claimed": 4.5, "itc_available_2a": 3.2, "mismatch_pct": 40.6},
            "Q2-FY24": {"itc_claimed": 5.1, "itc_available_2a": 4.8, "mismatch_pct": 6.25},
            "Q3-FY24": {"itc_claimed": 4.8, "itc_available_2a": 4.1, "mismatch_pct": 17.0},
            "Q4-FY24": {"itc_claimed": 3.8, "itc_available_2a": 4.2, "mismatch_pct": -9.5}
        },
        "circular_graph_data": {
            "nodes": [
                {"id": "TARGET", "label": "Apex Textiles", "type": "main"},
                {"id": "GSTIN-SUP-001", "label": "Tex-Supply Co", "type": "circular"},
                {"id": "GSTIN-SUP-002", "label": "Cotton Hub", "type": "supplier"},
                {"id": "GSTIN-BUY-001", "label": "Retail-Corp", "type": "buyer"}
            ],
            "edges": [
                {"from": "GSTIN-SUP-001", "to": "TARGET", "value": 1.2, "type": "purchase"},
                {"from": "TARGET", "to": "GSTIN-SUP-001", "value": 0.8, "type": "sale"},
                {"from": "GSTIN-SUP-002", "to": "TARGET", "value": 2.5, "type": "purchase"},
                {"from": "TARGET", "to": "GSTIN-BUY-001", "value": 3.1, "type": "sale"}
            ]
        }
    },

    # ── Bank Statement Analysis (last 12 months) ──────────────────────────
    "bank_statement": {
        "avg_balance_cr":          1.80,   # ₹ Crore
        "emi_outflow_monthly_cr":  0.42,   # Monthly loan outflows
        "peak_balance_cr":         4.10,
        "regular_credits":         True,   # 11/12 months had customer credits
    },

    # ── Confidence & Audit Trail ──────────────────────────────────────────
    "extraction_confidence": 0.91,         # 91% confident in extractions

    "source_citations": {
        "revenue_cr":          "Profit & Loss, Page 3: 'Revenue from operations 42.5 Cr'",
        "ebitda_cr":           "Profit & Loss, Page 3: 'EBITDA 6.1 Cr'",
        "net_profit_cr":       "Profit & Loss, Page 3: 'Profit for the year 2.3 Cr'",
        "total_assets_cr":     "Balance Sheet, Page 5: 'Total Assets 38.0 Cr'",
        "total_liabilities_cr":"Balance Sheet, Page 5: 'Total Liabilities 24.0 Cr'",
        "net_worth_cr":        "Balance Sheet, Page 5: 'Total Equity 14.0 Cr'",
        "dscr":             "Computed: EBITDA / (Interest ₹1.8Cr + Principal ₹5.0Cr)",
        "current_ratio":    "Balance Sheet, Page 6: 'Current Ratio 1.10'",
        "debt_to_equity":   "Computed: Total Debt 24.0 / Net Worth 14.0",
        "interest_coverage":"Profit & Loss, Page 4: 'ICR 2.40'",
    },

    # ── Feature 2: Structured citations (rich provenance) ─────────────────
    "source_citations_structured": {
        "revenue_cr": {
            "value": 42.5, "unit": "Cr", "source_page": 3,
            "source_statement": "Profit & Loss", "confidence": 0.94,
            "context": "Revenue from operations 42.50 Cr for the year ended 31st March 2024",
            "method": "regex",
        },
        "ebitda_cr": {
            "value": 6.1, "unit": "Cr", "source_page": 3,
            "source_statement": "Profit & Loss", "confidence": 0.94,
            "context": "EBITDA 6.10 Cr (EBIT + Depreciation 0.8 Cr)",
            "method": "regex",
        },
        "net_profit_cr": {
            "value": 2.3, "unit": "Cr", "source_page": 3,
            "source_statement": "Profit & Loss", "confidence": 0.94,
            "context": "Profit for the year (after tax) 2.30 Cr",
            "method": "regex",
        },
        "total_assets_cr": {
            "value": 38.0, "unit": "Cr", "source_page": 5,
            "source_statement": "Balance Sheet", "confidence": 0.94,
            "context": "Total Assets 38.00 Cr",
            "method": "regex",
        },
        "total_liabilities_cr": {
            "value": 24.0, "unit": "Cr", "source_page": 5,
            "source_statement": "Balance Sheet", "confidence": 0.94,
            "context": "Total Liabilities 24.00 Cr",
            "method": "regex",
        },
        "net_worth_cr": {
            "value": 14.0, "unit": "Cr", "source_page": 5,
            "source_statement": "Balance Sheet", "confidence": 0.80,
            "context": "Computed: Total Assets 38.0 − Total Liabilities 24.0",
            "method": "computed",
        },
        "dscr": {
            "value": 0.89, "unit": "ratio", "source_page": None,
            "source_statement": "Computed", "confidence": 0.80,
            "context": "EBITDA 6.1 / (Interest 1.8 + Annual Principal 5.0)",
            "method": "computed",
        },
        "current_ratio": {
            "value": 1.10, "unit": "ratio", "source_page": 6,
            "source_statement": "Balance Sheet", "confidence": 0.94,
            "context": "Current Ratio 1.10 (Current Assets 19.8 / Current Liabilities 18.0)",
            "method": "regex",
        },
        "debt_to_equity": {
            "value": 1.71, "unit": "ratio", "source_page": None,
            "source_statement": "Computed", "confidence": 0.80,
            "context": "Total Debt 24.0 / Net Worth 14.0",
            "method": "computed",
        },
        "interest_coverage": {
            "value": 2.40, "unit": "ratio", "source_page": 4,
            "source_statement": "Profit & Loss", "confidence": 0.94,
            "context": "Interest Coverage Ratio 2.40 (EBIT / Finance Costs)",
            "method": "regex",
        },
    },

    # ── Multi-Year Trend Data (Feature 1) ─────────────────────────────────
    # Story: Revenue declining since FY22, DSCR trending down through 1.25
    "multi_year_financials": {
        "FY22": {
            "revenue_cr":        51.2,
            "ebitda_cr":          9.8,
            "net_profit_cr":      4.1,
            "total_assets_cr":   42.0,
            "net_worth_cr":      18.0,
            "dscr":               1.31,
            "current_ratio":      1.40,
            "debt_to_equity":     1.33,
            "interest_coverage":  3.20,
        },
        "FY23": {
            "revenue_cr":        46.8,
            "ebitda_cr":          7.9,
            "net_profit_cr":      3.2,
            "total_assets_cr":   39.5,
            "net_worth_cr":      16.2,
            "dscr":               1.08,
            "current_ratio":      1.22,
            "debt_to_equity":     1.44,
            "interest_coverage":  2.85,
        },
        "FY24": {
            "revenue_cr":        42.5,    # current year — matches financials dict
            "ebitda_cr":          6.1,
            "net_profit_cr":      2.3,
            "total_assets_cr":   38.0,
            "net_worth_cr":      14.0,
            "dscr":               0.89,   # below 1.25 RED FLAG
            "current_ratio":      1.10,
            "debt_to_equity":     1.71,
            "interest_coverage":  2.40,
        },
    },

    "yoy_changes": {
        "revenue_cr":       [{"from_year": "FY22", "to_year": "FY23", "pct_change": -8.59},
                             {"from_year": "FY23", "to_year": "FY24", "pct_change": -9.19}],
        "ebitda_cr":        [{"from_year": "FY22", "to_year": "FY23", "pct_change": -19.39},
                             {"from_year": "FY23", "to_year": "FY24", "pct_change": -22.78}],
        "net_profit_cr":    [{"from_year": "FY22", "to_year": "FY23", "pct_change": -21.95},
                             {"from_year": "FY23", "to_year": "FY24", "pct_change": -28.13}],
        "dscr":             [{"from_year": "FY22", "to_year": "FY23", "pct_change": -17.56},
                             {"from_year": "FY23", "to_year": "FY24", "pct_change": -17.59}],
        "current_ratio":    [{"from_year": "FY22", "to_year": "FY23", "pct_change": -12.86},
                             {"from_year": "FY23", "to_year": "FY24", "pct_change": -9.84}],
    },

    "trend_signals": [
        {
            "level": 2,
            "signal": "Revenue declining for 2 consecutive years — YoY changes: ['-8.6%', '-9.2%']",
            "category": "revenue_trend",
            "field": "revenue_cr",
        },
        {
            "level": 2,
            "signal": "DSCR 0.89 below 1.0 — company cannot service debt from operating income (RBI threshold: 1.25)",
            "category": "debt_serviceability",
            "field": "dscr",
        },
        {
            "level": 1,
            "signal": "DSCR deteriorating consistently over 3 years (FY22→FY23: -17.6%, FY23→FY24: -17.6%)",
            "category": "debt_serviceability",
            "field": "dscr",
        },
        {
            "level": 1,
            "signal": "Current ratio 1.10, below RBI preferred minimum of 1.33",
            "category": "liquidity",
            "field": "current_ratio",
        },
    ],

    # ── Feature 3: Early Warning Signals (RBI EWS Framework) ──────────────
    # Sorted by severity (Level 3 first → Level 1 last)
    "early_warning_signals": [
        # Level 2 signals
        {
            "level": 2,
            "signal": "DSCR 0.89 below 1.0 — operating income cannot cover debt service obligations (RBI threshold: 1.25)",
            "category": "debt_serviceability",
            "field": "dscr",
            "threshold": "< 1.0",
        },
        {
            "level": 2,
            "signal": "GST ITC mismatch 18.2% — exceeds 15.0% threshold, indicating potential input tax credit fraud",
            "category": "gst_compliance",
            "field": "gst_mismatch_pct",
            "threshold": "> 15.0%",
        },
        {
            "level": 2,
            "signal": "Monthly EMI ₹0.42 Cr is 23% of avg balance ₹1.80 Cr — limited liquidity buffer",
            "category": "banking_behaviour",
            "field": "emi_outflow_monthly_cr",
            "threshold": "EMI > 50% of avg_balance",
        },
        {
            "level": 2,
            "signal": "Revenue declining for 2 consecutive years — YoY changes: ['-8.6%', '-9.2%']",
            "category": "revenue_trend",
            "field": "revenue_cr",
            "threshold": "trend-based",
        },
        # Level 1 signals
        {
            "level": 1,
            "signal": "Current ratio 1.10 below RBI norm of 1.33 — liquidity under pressure",
            "category": "liquidity",
            "field": "current_ratio",
            "threshold": "< 1.33",
        },
        {
            "level": 1,
            "signal": "Interest Coverage Ratio 2.40x below preferred minimum of 2.5x",
            "category": "debt_serviceability",
            "field": "interest_coverage",
            "threshold": "< 2.5",
        },
        {
            "level": 1,
            "signal": "Net profit margin 5.4% — very thin margin (< 2% signals fragile profitability)",
            "category": "profitability",
            "field": "net_profit_cr",
            "threshold": "margin < 2%",
        },
    ],
}


# ---------------------------------------------------------------------------
# DEMO SCENARIO 2: Sunrise Foods Pvt Ltd
# Decision will be: LEND (score ~78/100)
# Key signals: Strong DSCR, clean GST, no litigation
# ---------------------------------------------------------------------------

HEALTHY_COMPANY_DOC_REPORT = {
    "company_name": "Sunrise Foods Pvt Ltd",
    "gstin": "29AAZCS4321G1ZK",

    "financials": {
        "revenue_cr":           88.0,
        "ebitda_cr":            14.5,
        "net_profit_cr":         7.2,
        "total_assets_cr":      62.0,
        "total_liabilities_cr": 28.0,
        "net_worth_cr":         34.0,
        "dscr":                  1.82,  # Well above 1.25 ← STRONG
        "current_ratio":         1.55,
        "debt_to_equity":        0.82,
        "interest_coverage":     4.10,
    },

    "gst_analysis": {
        "mismatch_pct":            3.1,      # <5% → GREEN
        "mismatch_flag":           "GREEN",
        "circular_trading_flag":   False,
        "revenue_inflation_flag":  False,
        "gst_score":               20,       # out of 20
    },

    "bank_statement": {
        "avg_balance_cr":          4.20,
        "emi_outflow_monthly_cr":  0.65,
        "peak_balance_cr":         9.80,
        "regular_credits":         True,
    },

    "extraction_confidence": 0.95,

    "source_citations": {
        "revenue":          "P&L Statement FY2024, Page 2, Line 5",
        "ebitda":           "P&L Statement FY2024, Page 2, Line 11",
        "net_profit":       "P&L Statement FY2024, Page 2, Line 17",
        "total_assets":     "Balance Sheet FY2024, Page 4, Line 3",
        "total_liabilities":"Balance Sheet FY2024, Page 4, Line 8",
        "net_worth":        "Balance Sheet FY2024, Page 4, Line 14",
        "dscr":             "Computed: EBITDA / (Interest ₹2.1Cr + Principal ₹5.9Cr)",
        "current_ratio":    "Balance Sheet FY2024, Page 5",
        "gst_mismatch":     "GSTR-3B Q1-Q4 FY2024 vs GSTR-2A cross-validation",
        "avg_balance":      "Bank Statement HDFC A/C ****8812, Apr 2023 – Mar 2024",
    },

    # ── Multi-Year Trend Data (Feature 1) ─────────────────────────────────
    # Story: Consistently improving across all 3 years → strong LEND signal
    "multi_year_financials": {
        "FY22": {
            "revenue_cr":        71.2,
            "ebitda_cr":         10.8,
            "net_profit_cr":      5.1,
            "total_assets_cr":   52.0,
            "net_worth_cr":      27.0,
            "dscr":               1.55,
            "current_ratio":      1.38,
            "debt_to_equity":     0.93,
            "interest_coverage":  3.50,
        },
        "FY23": {
            "revenue_cr":        79.5,
            "ebitda_cr":         12.4,
            "net_profit_cr":      6.1,
            "total_assets_cr":   57.0,
            "net_worth_cr":      30.5,
            "dscr":               1.68,
            "current_ratio":      1.46,
            "debt_to_equity":     0.87,
            "interest_coverage":  3.82,
        },
        "FY24": {
            "revenue_cr":        88.0,    # current year — matches financials dict
            "ebitda_cr":         14.5,
            "net_profit_cr":      7.2,
            "total_assets_cr":   62.0,
            "net_worth_cr":      34.0,
            "dscr":               1.82,
            "current_ratio":      1.55,
            "debt_to_equity":     0.82,
            "interest_coverage":  4.10,
        },
    },

    "yoy_changes": {
        "revenue_cr":    [{"from_year": "FY22", "to_year": "FY23", "pct_change": +11.65},
                          {"from_year": "FY23", "to_year": "FY24", "pct_change": +10.69}],
        "ebitda_cr":     [{"from_year": "FY22", "to_year": "FY23", "pct_change": +14.81},
                          {"from_year": "FY23", "to_year": "FY24", "pct_change": +16.94}],
        "net_profit_cr": [{"from_year": "FY22", "to_year": "FY23", "pct_change": +19.61},
                          {"from_year": "FY23", "to_year": "FY24", "pct_change": +18.03}],
        "dscr":          [{"from_year": "FY22", "to_year": "FY23", "pct_change": +8.39},
                          {"from_year": "FY23", "to_year": "FY24", "pct_change": +8.33}],
    },

    # No EWS signals — healthy company with strong improving trends
    "trend_signals": [],

    # Healthy company — no early warning signals fired
    "early_warning_signals": [],
}


# ---------------------------------------------------------------------------
# Helper to export as JSON (call this to generate demo_data/*.json files)
# ---------------------------------------------------------------------------

def export_to_json():
    """Exports both mock reports to demo_data/ for M4 (Frontend) to use."""
    import json
    import os

    output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "demo_data")
    os.makedirs(output_dir, exist_ok=True)

    apex_path = os.path.join(output_dir, "apex_textiles_document.json")
    sunrise_path = os.path.join(output_dir, "sunrise_foods_document.json")

    with open(apex_path, "w") as f:
        json.dump(APEX_TEXTILES_DOC_REPORT, f, indent=2)
    with open(sunrise_path, "w") as f:
        json.dump(HEALTHY_COMPANY_DOC_REPORT, f, indent=2)

    print(f"[mock_data] Exported:\n  {apex_path}\n  {sunrise_path}")


if __name__ == "__main__":
    export_to_json()
