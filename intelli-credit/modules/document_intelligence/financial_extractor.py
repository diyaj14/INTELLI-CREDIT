"""
financial_extractor.py — Module 1: Document Intelligence
=========================================================
Extracts financial metrics from parsed PDF text and computes credit ratios.

Two strategies (in order):
  1. Regex patterns tuned for Indian CA-certified financial statements
  2. Gemini Flash fallback when regex yields None

Produces:
  - financials dict   (all 10 CONTRACT 1 fields)
  - source_citations  (page + context reference per field)
  - extraction_confidence (0–1)

Usage:
    from modules.document_intelligence.pdf_ingestor import PDFIngestor
    from modules.document_intelligence.financial_extractor import FinancialExtractor

    ingest_result = PDFIngestor().ingest("annual_report.pdf")
    extractor = FinancialExtractor(ingest_result["raw_text"], ingest_result["tables"])
    result = extractor.extract_all()
    # result = {"financials": {...}, "source_citations": {...}, "confidence": 0.87}
"""

import re
import os
import logging
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns for Indian financial statements
# These cover:
#   - Standard Ind AS formats
#   - Schedule VI formats (older companies)
#   - CA-certified formats with ₹, Rs., Rs crore, lakhs annotations
# ─────────────────────────────────────────────────────────────────────────────

# Normalises numbers like "42,50,000" → 42.5  (assuming crore unit)
# or "42.50" → 42.50  (already in crores)
def _parse_indian_number(raw: str) -> Optional[float]:
    """
    Parses Indian-format numbers into a float.
    Handles: "42,50,00,000", "42.50 Crore", "6,10,00,000", "2,345.67"
    Always returns value in CRORE units.
    """
    if not raw:
        return None
    raw = raw.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    raw = raw.strip()

    # Detect unit from surrounding context (handled upstream, fallback here)
    if "crore" in raw.lower() or "cr" in raw.lower():
        raw = re.sub(r'(?i)(crores?|cr\.?)', '', raw).strip()
        try:
            return round(float(raw), 2)
        except ValueError:
            return None

    if "lakh" in raw.lower():
        raw = re.sub(r'(?i)(lakhs?)', '', raw).strip()
        try:
            return round(float(raw) / 100, 2)  # convert lakhs → crores
        except ValueError:
            return None

    # Plain number — try to auto-detect scale
    try:
        val = float(raw)
        # Heuristic: if value > 10,000 it's likely in lakhs; if > 1,000,000 in rupees
        if val > 10_000_000:   # > 1 crore in rupees
            return round(val / 10_000_000, 2)
        elif val > 100_000:    # > 1 lakh in rupees
            return round(val / 10_000_000, 2)
        else:
            return round(val, 2)  # assume already in crores
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pattern registry — ordered from most to least specific
# ─────────────────────────────────────────────────────────────────────────────

FIELD_PATTERNS = {

    "revenue_cr": [
        # Standard P&L line items
        r"(?i)revenue\s+from\s+operations[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)net\s+revenue[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)total\s+revenue[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)turnover[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)sales[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)income\s+from\s+operations[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "ebitda_cr": [
        r"(?i)ebitda[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)earnings\s+before\s+interest.*?depreciation[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)operating\s+profit[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)profit\s+before\s+interest.*?depreciation[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "net_profit_cr": [
        r"(?i)profit\s+after\s+tax[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)net\s+profit[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)profit\s+for\s+the\s+year[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)pat[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)net\s+income[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "total_assets_cr": [
        r"(?i)total\s+assets[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)total\s+of\s+assets[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "total_liabilities_cr": [
        r"(?i)total\s+liabilities[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)total\s+of\s+liabilities[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)borrowings\s*(?:and\s+other\s+liabilities)?[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "net_worth_cr": [
        r"(?i)net\s+worth[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)shareholders['']?\s*equity[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)total\s+equity[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)net\s+owned\s+funds[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    # Ratios — look for direct mention (some reports include a ratio table)
    "current_ratio": [
        r"(?i)current\s+ratio[^\d]*?([\d,\.]+)",
        r"(?i)cr\s*:\s*([\d,\.]+)",          # CR: 1.10
    ],

    "debt_to_equity": [
        r"(?i)debt\s*[/-]\s*equity\s+ratio[^\d]*?([\d,\.]+)",
        r"(?i)d\s*/\s*e\s+ratio[^\d]*?([\d,\.]+)",
        r"(?i)debt\s+to\s+equity[^\d]*?([\d,\.]+)",
    ],

    "interest_coverage": [
        r"(?i)interest\s+coverage\s+ratio[^\d]*?([\d,\.]+)",
        r"(?i)icr[^\d]*?([\d,\.]+)",
        r"(?i)times\s+interest\s+earned[^\d]*?([\d,\.]+)",
    ],

    # DSCR is rarely printed — we compute it from components
    # These patterns are for when a report DOES include it
    "dscr": [
        r"(?i)dscr[^\d]*?([\d,\.]+)",
        r"(?i)debt\s+service\s+coverage[^\d]*?([\d,\.]+)",
    ],

    # For DSCR computation — not a final field but needed intermediates
    "_interest_expense_cr": [
        r"(?i)finance\s+costs?[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)interest\s+(?:expense|paid|cost)[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)borrowing\s+costs?[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "_depreciation_cr": [
        r"(?i)depreciation[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)amortisation[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)d&a[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "_current_assets_cr": [
        r"(?i)total\s+current\s+assets[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)current\s+assets[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "_current_liabilities_cr": [
        r"(?i)total\s+current\s+liabilities[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)current\s+liabilities[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],

    "_total_debt_cr": [
        r"(?i)total\s+(?:long.term\s+)?borrowings?[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
        r"(?i)total\s+debt[^\d]*?([\d,\.]+)\s*(?:crores?|cr\.?|lakh)?",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Multi-year detection helpers
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that identify a fiscal year column header in Indian annual reports
FY_YEAR_PATTERNS = [
    r"(?:FY|F\.Y\.|Financial\s+Year)[\s\-\.]*([\d]{2,4})[\-\/]([\d]{2,4})",  # FY2023-24 / FY 22-23
    r"([\d]{4})[\-\/]([\d]{2,4})",                                              # 2023-24 / 2022-23
    r"Year\s+ended\s+(?:March|Mar)\s+[0-9]+,?\s*([\d]{4})",                    # Year ended March 31, 2024
    r"(?:31st?\s+March|March\s+31st?)[,\s]*([\d]{4})",                          # 31st March 2024
]

# Keywords for each metric in multi-year table rows
TREND_FIELD_KEYWORDS: Dict[str, List[str]] = {
    "revenue_cr":           ["revenue", "turnover", "net sales", "income from operations"],
    "ebitda_cr":            ["ebitda", "operating profit", "profit before interest"],
    "net_profit_cr":        ["profit after tax", "net profit", "pat", "profit for the year"],
    "total_assets_cr":      ["total assets"],
    "net_worth_cr":         ["net worth", "shareholders equity", "total equity"],
    "dscr":                 ["dscr", "debt service coverage"],
    "current_ratio":        ["current ratio"],
    "debt_to_equity":       ["debt equity", "debt to equity", "d/e"],
    "interest_coverage":    ["interest coverage", "icr", "times interest earned"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────────────────────────────────────

class FinancialExtractor:
    """
    Extracts financial metrics from PDF-parsed text.
    Falls back to Gemini when regex patterns don't match.
    """

    # Fields that must be found for the extractor to claim high confidence
    REQUIRED_FIELDS = [
        "revenue_cr", "net_profit_cr", "total_assets_cr",
        "total_liabilities_cr", "net_worth_cr",
    ]

    # Statement type keywords
    _BS_KEYWORDS = ["balance sheet", "statement of assets and liabilities", "financial position"]
    _PL_KEYWORDS = ["profit and loss", "profit & loss", "income statement", "statement of operations"]

    def __init__(self, raw_text: dict[int, str], tables: list[pd.DataFrame]):
        """
        Args:
            raw_text: dict mapping page numbers (1-indexed) to their text content.
            tables: list of pandas DataFrames extracted from the document.
        """
        self.raw_text = raw_text
        self.tables = tables or []
        self.page_types = self._detect_page_types()
        self._gemini_model = None  # lazy-loaded

        # Stores results and metadata
        self._extracted: dict = {}
        self._citations: dict = {}           # plain-string citations (backward compat)
        self._citations_structured: dict = {}  # rich citation objects (Feature 2)
        self._methods: dict = {}   # "regex" | "llm" | "computed" | "default"

    def _detect_page_types(self) -> dict[int, str]:
        """Detects if a page belongs to 'Balance Sheet', 'Profit & Loss', or 'Other'."""
        types = {}
        for pg, text in self.raw_text.items():
            lower_text = text.lower()
            if any(kw in lower_text for kw in self._PL_KEYWORDS):
                types[pg] = "Profit & Loss"
            elif any(kw in lower_text for kw in self._BS_KEYWORDS):
                types[pg] = "Balance Sheet"
            else:
                types[pg] = "Financial Statement"
        return types

    def _get_citation_prefix(self, page_num: int) -> str:
        """Returns a string like 'Balance Sheet, Page 4' (fallbacks to 'Financial Statement, Page X')."""
        st_type = self.page_types.get(page_num, "Financial Statement")
        return f"{st_type}, Page {page_num}"

    def _make_citation(
        self,
        value: float,
        field_name: str,
        page_num: Optional[int],
        context: str,
        method: str,
    ) -> dict:
        """
        Builds a structured citation object for a single extracted field.

        Format (WOW FACTOR #3 — explainable rejection with source citations):
          {
            "value":            42.3,
            "unit":             "Cr",
            "source_page":      4,
            "source_statement": "Profit & Loss",
            "confidence":       0.94,
            "context":          "Revenue from operations 42.50 Cr (FY2024)",
            "method":           "regex" | "table" | "llm" | "computed" | "default"
          }
        """
        # Determine unit
        if field_name.endswith("_cr"):
            unit = "Cr"
        elif field_name in ("current_ratio", "debt_to_equity",
                            "interest_coverage", "dscr"):
            unit = "ratio"
        else:
            unit = ""

        # Map method → confidence level
        method_confidence = {
            "regex":    0.94,
            "table":    0.85,
            "llm":      0.70,
            "computed": 0.80,
            "default":  0.20,
        }

        st_type = self.page_types.get(page_num, "Financial Statement") if page_num else "Computed"

        return {
            "value":            round(value, 3),
            "unit":             unit,
            "source_page":      page_num,
            "source_statement": st_type,
            "confidence":       method_confidence.get(method, 0.5),
            "context":          context.strip()[:120] if context else "",
            "method":           method,
        }

    # ── Regex Extraction ───────────────────────────────────────────────────────

    def extract_field_regex(self, field_name: str) -> tuple[Optional[float], str]:
        """
        Tries all regex patterns for a field across all pages.

        Returns:
            (value_in_crores, citation_string)
            or (None, "") if not found
        """
        patterns = FIELD_PATTERNS.get(field_name, [])
        if not patterns:
            return None, ""

        # Try each page individually to build accurate citations
        for page_num in sorted(self.raw_text.keys()):
            page_text = self.raw_text[page_num]

            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    raw_val = match.group(1)
                    # Determine unit from surrounding context (±50 chars)
                    start = max(0, match.start() - 30)
                    end = min(len(page_text), match.end() + 30)
                    context = page_text[start:end]

                    # Determine unit
                    in_lakhs = bool(re.search(r'(?i)lakh', context))
                    in_crores = bool(re.search(r'(?i)crore|cr\.', context))

                    try:
                        val = float(raw_val.replace(",", ""))
                        if in_lakhs and not in_crores:
                            val = round(val / 100, 2)
                        elif val > 10_000_000:
                            val = round(val / 10_000_000, 2)
                        elif val > 100_000 and not in_crores:
                            val = round(val / 10_000_000, 2)
                        else:
                            val = round(val, 2)
                    except ValueError:
                        continue

                    # Reject clearly wrong values (negative revenue, etc.)
                    if field_name.endswith("_cr") and not field_name.startswith("_"):
                        if val <= 0:
                            continue

                    prefix = self._get_citation_prefix(page_num)
                    citation_str = f"{prefix}: '{context.strip()[:80]}'"

                    # Build structured citation and store it
                    structured = self._make_citation(val, field_name, page_num, context, "regex")
                    self._citations_structured[field_name] = structured

                    logger.debug(f"[regex] {field_name} = {val} | {citation_str}")
                    return val, citation_str

        return None, ""

    # ── Table-Based Extraction ─────────────────────────────────────────────────

    def _search_tables(self, keywords: list[str]) -> Optional[float]:
        """
        Searches extracted DataFrames for rows matching keywords.
        Returns the first numeric value found in the adjacent cell.
        """
        for df in self.tables:
            if df.empty:
                continue
            df_str = df.astype(str)
            for _, row in df_str.iterrows():
                row_text = " ".join(row.values).lower()
                if any(kw.lower() in row_text for kw in keywords):
                    # Find first numeric cell in this row
                    for cell in row.values:
                        cleaned = str(cell).replace(",", "").replace("₹", "").strip()
                        try:
                            val = float(cleaned)
                            if val > 0:
                                # Scale to crores if needed
                                if val > 10_000_000:
                                    return round(val / 10_000_000, 2)
                                return round(val, 2)
                        except ValueError:
                            continue
        return None

    # ── Gemini Fallback ───────────────────────────────────────────────────────

    def _load_gemini(self):
        """Lazy-loads Gemini. Reads API key from environment."""
        if self._gemini_model is not None:
            return self._gemini_model

        try:
            import google.generativeai as genai
            from dotenv import load_dotenv
            load_dotenv()

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set — LLM fallback unavailable")
                return None

            genai.configure(api_key=api_key)
            self._gemini_model = genai.GenerativeModel("gemini-1.5-flash")
            logger.info("Gemini Flash model loaded for LLM fallback")
        except ImportError:
            logger.warning("google-generativeai not installed — LLM fallback unavailable")
        except Exception as e:
            logger.warning(f"Gemini load error: {e}")

        return self._gemini_model

    def extract_field_llm(self, field_name: str) -> tuple[Optional[float], str]:
        """
        Uses Gemini Flash to extract a field that regex couldn't find.
        Only sends the most relevant page text to avoid token limits.

        Returns:
            (value_in_crores, citation_string)
        """
        model = self._load_gemini()
        if model is None:
            return None, ""

        field_descriptions = {
            "revenue_cr":           "Revenue from Operations / Net Sales / Total Revenue",
            "ebitda_cr":            "EBITDA / Operating Profit / Profit before Interest and Depreciation",
            "net_profit_cr":        "Net Profit after Tax (PAT) / Profit for the Year",
            "total_assets_cr":      "Total Assets (from Balance Sheet)",
            "total_liabilities_cr": "Total Liabilities / Total Borrowings + Other Liabilities",
            "net_worth_cr":         "Net Worth / Shareholders Equity / Total Equity",
            "current_ratio":        "Current Ratio (dimensionless number, typically 1.0–2.5)",
            "debt_to_equity":       "Debt to Equity Ratio (dimensionless)",
            "interest_coverage":    "Interest Coverage Ratio / Times Interest Earned (dimensionless)",
            "dscr":                 "Debt Service Coverage Ratio DSCR",
            "_interest_expense_cr": "Finance Costs / Interest Expense / Borrowing Costs",
            "_depreciation_cr":     "Depreciation and Amortisation (D&A)",
            "_current_assets_cr":   "Total Current Assets",
            "_current_liabilities_cr": "Total Current Liabilities",
            "_total_debt_cr":       "Total Borrowings / Total Debt",
        }

        description = field_descriptions.get(field_name, field_name)

        # Use only the most relevant pages (first 5 pages of the document)
        sample_text = "\n\n---PAGE BREAK---\n\n".join(
            [self.raw_text.get(p, "") for p in sorted(self.raw_text.keys())[:6]]
        )
        sample_text = sample_text[:8000]  # stay within token budget

        prompt = f"""You are a financial analyst reading an Indian corporate annual report.

Extract the value for: {description}

Rules:
- Return ONLY a number in Indian Rupees CRORE (e.g. 42.5 means Rs. 42.5 Crore)
- If the document value is in Lakhs, convert to Crores (divide by 100)
- If the document value is raw rupees (e.g. 425000000), convert to Crores (divide by 10000000)
- For ratios (current_ratio, d/e, icr, dscr): return the ratio number as-is (no unit conversion)
- If you cannot find the value, return exactly: NOT_FOUND
- Return ONLY the number or NOT_FOUND. No explanation.

Document Text:
{sample_text}
"""

        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            logger.debug(f"[Gemini] {field_name} → raw response: '{raw}'")

            if "NOT_FOUND" in raw.upper() or not raw:
                return None, ""

            # Extract first number from response
            numbers = re.findall(r"[\d,\.]+", raw)
            if not numbers:
                return None, ""

            val = float(numbers[0].replace(",", ""))
            citation_str = "LLM extraction (Gemini Flash) — verify manually"

            # Build structured citation for LLM extraction
            structured = self._make_citation(round(val, 2), field_name, None, "LLM extraction via Gemini Flash", "llm")
            self._citations_structured[field_name] = structured

            logger.info(f"[Gemini] {field_name} = {val}")
            return round(val, 2), citation_str

        except Exception as e:
            logger.warning(f"Gemini extraction failed for {field_name}: {e}")
            return None, ""

    # ── Ratio Computation ─────────────────────────────────────────────────────

    def compute_ratios(self) -> dict:
        """
        Computes derived ratios from extracted raw fields.
        Uses formula first; falls back to extracted value if formula is impossible.

        Returns dict of ratios with their sources.
        """
        ratios = {}
        ratio_citations = {}

        ext = self._extracted

        # ── Current Ratio = Current Assets / Current Liabilities ─────────────
        ca = ext.get("_current_assets_cr")
        cl = ext.get("_current_liabilities_cr")
        if ca and cl and cl != 0:
            ratios["current_ratio"] = round(ca / cl, 2)
            ratio_citations["current_ratio"] = f"Computed: Current Assets {ca} / Current Liabilities {cl}"
        elif ext.get("current_ratio"):
            ratios["current_ratio"] = ext["current_ratio"]
            ratio_citations["current_ratio"] = self._citations.get("current_ratio", "Extracted directly")
        else:
            ratios["current_ratio"] = 1.0  # conservative default
            ratio_citations["current_ratio"] = "Default (could not compute)"
            logger.warning("current_ratio could not be computed or extracted — using default 1.0")

        # ── Debt to Equity = Total Debt / Net Worth ────────────────────────────
        debt = ext.get("_total_debt_cr")
        nw = ext.get("net_worth_cr")
        if debt and nw and nw != 0:
            ratios["debt_to_equity"] = round(debt / nw, 2)
            ratio_citations["debt_to_equity"] = f"Computed: Total Debt {debt} / Net Worth {nw}"
        elif ext.get("debt_to_equity"):
            ratios["debt_to_equity"] = ext["debt_to_equity"]
            ratio_citations["debt_to_equity"] = self._citations.get("debt_to_equity", "Extracted directly")
        else:
            # Estimate: (Total Liabilities - Current Liabilities) / Net Worth
            tl = ext.get("total_liabilities_cr")
            if tl and nw and nw != 0:
                est_debt = tl * 0.6  # rough: ~60% of total liabilities is long-term
                ratios["debt_to_equity"] = round(est_debt / nw, 2)
                ratio_citations["debt_to_equity"] = "Estimated: 60% of Total Liabilities / Net Worth"
            else:
                ratios["debt_to_equity"] = 1.5  # moderate default
                ratio_citations["debt_to_equity"] = "Default (could not compute)"

        # ── Interest Coverage = EBIT / Interest Expense ───────────────────────
        ebitda = ext.get("ebitda_cr")
        dep = ext.get("_depreciation_cr", 0) or 0
        interest = ext.get("_interest_expense_cr")
        ebit = (ebitda - dep) if (ebitda and ebitda > dep) else ebitda

        if ebit and interest and interest != 0:
            ratios["interest_coverage"] = round(ebit / interest, 2)
            ratio_citations["interest_coverage"] = f"Computed: EBIT {round(ebit,2)} / Interest {interest}"
        elif ext.get("interest_coverage"):
            ratios["interest_coverage"] = ext["interest_coverage"]
            ratio_citations["interest_coverage"] = self._citations.get("interest_coverage", "Extracted directly")
        else:
            ratios["interest_coverage"] = 2.0
            ratio_citations["interest_coverage"] = "Default (could not compute)"

        # ── DSCR = EBITDA / (Interest + Annual Principal) ─────────────────────
        # Annual principal is hard to extract without a loan schedule.
        # Approximation: Total Debt / 5 (assuming 5-year average tenure)
        if ebitda and interest:
            annual_principal = (debt / 5) if debt else 0
            denominator = interest + annual_principal
            if denominator > 0:
                ratios["dscr"] = round(ebitda / denominator, 2)
                ratio_citations["dscr"] = (
                    f"Computed: EBITDA {ebitda} / "
                    f"(Interest {interest} + Est. Principal {round(annual_principal,2)})"
                )
            else:
                ratios["dscr"] = ext.get("dscr", 1.0)
                ratio_citations["dscr"] = "Default (denominator zero)"
        elif ext.get("dscr"):
            ratios["dscr"] = ext["dscr"]
            ratio_citations["dscr"] = self._citations.get("dscr", "Extracted directly")
        else:
            ratios["dscr"] = 1.0
            ratio_citations["dscr"] = "Default (could not compute)"

        # -- Structured citations for computed ratios (Feature 2) ──────────────
        self._citations_structured["current_ratio"] = self._make_citation(
            ratios["current_ratio"], "current_ratio", None,
            ratio_citations["current_ratio"], "computed"
        )
        self._citations_structured["debt_to_equity"] = self._make_citation(
            ratios["debt_to_equity"], "debt_to_equity", None,
            ratio_citations["debt_to_equity"], "computed"
        )
        self._citations_structured["interest_coverage"] = self._make_citation(
            ratios["interest_coverage"], "interest_coverage", None,
            ratio_citations["interest_coverage"], "computed"
        )
        self._citations_structured["dscr"] = self._make_citation(
            ratios["dscr"], "dscr", None,
            ratio_citations["dscr"], "computed"
        )

        return ratios, ratio_citations

    # ── Confidence Scoring ────────────────────────────────────────────────────

    def confidence_score(self) -> float:
        """
        Returns 0–1 confidence based on:
        - How many required fields were successfully extracted (vs defaulted)
        - Whether critical fields used regex (high) vs LLM (medium) vs default (low)
        """
        weights = {
            "regex": 1.0,
            "llm": 0.7,
            "computed": 0.8,
            "table": 0.85,
            "default": 0.2,
        }

        required = self.REQUIRED_FIELDS
        if not required:
            return 0.5

        total_weight = 0.0
        for field in required:
            method = self._methods.get(field, "default")
            total_weight += weights.get(method, 0.2)

        return round(total_weight / len(required), 3)

    # ── Multi-Year Trend Analysis ─────────────────────────────────────────────

    def extract_multi_year(self) -> Dict[str, Dict[str, Optional[float]]]:
        """
        Attempts to extract key financial metrics across multiple fiscal years
        (FY22, FY23, FY24) from comparative tables in annual reports.

        Strategy:
          1. Scan all pages for year-column headers (FY2022-23, 2023-24, etc.)
          2. For pages with multi-year columns, extract metric rows by keyword
          3. Assign values to the detected year columns

        Returns:
            Dict keyed by canonical year label (e.g. "FY22", "FY23", "FY24")
            Each value is a dict of metric_name → float (in crores) or None
        """
        results: Dict[str, Dict[str, Optional[float]]] = {}

        for page_num in sorted(self.raw_text.keys()):
            page_text = self.raw_text[page_num]
            # Detect year headers on this page
            year_labels = self._detect_year_columns(page_text)
            if len(year_labels) < 2:
                continue  # need at least 2 years for comparison

            # Try to extract each metric's row values for detected years
            for field, keywords in TREND_FIELD_KEYWORDS.items():
                for kw in keywords:
                    row_match = self._find_metric_row(page_text, kw)
                    if row_match:
                        # Extract all numbers from this row
                        nums = re.findall(r"[\d,\.]{3,}", row_match)
                        nums_f = []
                        for n in nums:
                            try:
                                v = float(n.replace(",", ""))
                                if v > 0:
                                    nums_f.append(v)
                            except ValueError:
                                pass

                        # Align numbers to the year columns we detected
                        for i, yr_label in enumerate(year_labels):
                            if i < len(nums_f):
                                val = nums_f[i]
                                # Scale to crores if needed (ratios stay as-is)
                                if field.endswith("_cr") and val > 10_000_000:
                                    val = round(val / 10_000_000, 2)
                                elif field.endswith("_cr") and val > 100_000:
                                    val = round(val / 10_000_000, 2)
                                else:
                                    val = round(val, 3)

                                if yr_label not in results:
                                    results[yr_label] = {}
                                # Only record first successful match per field/year
                                if field not in results[yr_label]:
                                    results[yr_label][field] = val
                        break  # found row for this field — move to next field

        # Always ensure the current-year data is present (from single-year extraction)
        if self._extracted:
            current_yr = self._detect_current_year()
            if current_yr not in results:
                results[current_yr] = {}
            for field in TREND_FIELD_KEYWORDS:
                if field not in results[current_yr] and field in self._extracted:
                    results[current_yr][field] = self._extracted.get(field)

        logger.info(f"Multi-year extraction found data for years: {list(results.keys())}")
        return results

    def _detect_year_columns(self, text: str) -> List[str]:
        """
        Scans page text for fiscal year column headers.
        Returns list of canonical year labels like ["FY22", "FY23", "FY24"].
        """
        found_years = []
        seen = set()

        # Pattern 1: FY2023-24, FY 22-23
        for m in re.finditer(
            r"(?:FY|F\.Y\.|Financial\s+Year)[\s\-\.]*([\d]{2,4})[\-\/]([\d]{2,4})",
            text, re.IGNORECASE
        ):
            end_yr = m.group(2).strip()
            if len(end_yr) == 2:
                label = f"FY{end_yr}"
            else:
                label = f"FY{end_yr[2:]}"
            if label not in seen:
                seen.add(label)
                found_years.append(label)

        # Pattern 2: Standalone 2023-24 / 2022-23
        if not found_years:
            for m in re.finditer(r"([\d]{4})[\-\/]([\d]{2,4})", text):
                start_yr = m.group(1)
                end_yr_raw = m.group(2)
                if len(end_yr_raw) == 2:
                    label = f"FY{end_yr_raw}"
                else:
                    label = f"FY{end_yr_raw[2:]}"
                if label not in seen and int(start_yr) > 2010:
                    seen.add(label)
                    found_years.append(label)

        # Pattern 3: "Year ended March 2024"
        if not found_years:
            for m in re.finditer(
                r"(?:Year\s+ended.*?|31st?\s+March[,\s]+)([\d]{4})", text, re.IGNORECASE
            ):
                yr = m.group(1)
                label = f"FY{yr[2:]}"
                if label not in seen:
                    seen.add(label)
                    found_years.append(label)

        return sorted(found_years)  # sort chronologically

    def _detect_current_year(self) -> str:
        """Best-guess at the current/latest fiscal year from the document text."""
        all_text = " ".join(self.raw_text.values())
        years = []
        for m in re.finditer(r"FY[\s]?([\d]{2,4})[\-\/]([\d]{2,4})", all_text, re.IGNORECASE):
            try:
                yr = int(m.group(2).strip())
                if yr > 10:
                    years.append(yr if yr > 100 else yr + 2000)
            except ValueError:
                pass
        if years:
            latest = max(years)
            return f"FY{str(latest)[2:]}"  # e.g. "FY24"
        return "FY24"  # safe default

    def _find_metric_row(self, text: str, keyword: str) -> Optional[str]:
        """
        Finds a line in `text` that starts with or contains `keyword`,
        presumably a row in a multi-year financial table.
        Returns the raw line text so we can extract numbers from it.
        """
        for line in text.split("\n"):
            if keyword.lower() in line.lower():
                # Ensure the line has at least 2 numbers (multi-year data)
                if len(re.findall(r"[\d,\.]{3,}", line)) >= 2:
                    return line
        return None

    def compute_yoy_changes(
        self, multi_year: Dict[str, Dict[str, Optional[float]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Computes Year-over-Year % change for each metric across detected years.

        Returns:
            Dict mapping metric_name → list of {from_year, to_year, pct_change}
        """
        yoy: Dict[str, List[Dict[str, Any]]] = {}
        years = sorted(multi_year.keys())  # e.g. ["FY22", "FY23", "FY24"]

        for i in range(1, len(years)):
            yr_from = years[i - 1]
            yr_to   = years[i]
            data_from = multi_year.get(yr_from, {})
            data_to   = multi_year.get(yr_to, {})

            for field in TREND_FIELD_KEYWORDS:
                v_from = data_from.get(field)
                v_to   = data_to.get(field)
                if v_from is not None and v_to is not None and v_from != 0:
                    pct = round(((v_to - v_from) / abs(v_from)) * 100, 2)
                    if field not in yoy:
                        yoy[field] = []
                    yoy[field].append({
                        "from_year":  yr_from,
                        "to_year":    yr_to,
                        "pct_change": pct,
                    })

        return yoy

    def generate_trend_signals(
        self,
        multi_year: Dict[str, Dict[str, Optional[float]]],
        yoy: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        Generates RBI EWS-aligned trend signals from multi-year data.

        Signal format:
          {"level": 1|2|3, "signal": str, "category": str, "field": str}

        Levels (RBI EWS framework):
          Level 1 (Watch):          Early signs, monitor closely
          Level 2 (Special Mention): Significant deterioration
          Level 3 (Stress):          Severe — near NPA territory
        """
        signals: List[Dict[str, Any]] = []
        years = sorted(multi_year.keys())

        if len(years) < 2:
            return signals  # Not enough years for trend analysis

        latest_yr = years[-1]
        latest = multi_year.get(latest_yr, {})

        # ── Revenue trends ────────────────────────────────────────────────────
        rev_yoy = yoy.get("revenue_cr", [])
        declining_quarters = sum(1 for y in rev_yoy if y["pct_change"] < 0)
        if declining_quarters >= 2:
            yoy_str = str([f"{y['pct_change']:+.1f}%" for y in rev_yoy])
            signals.append({
                "level": 2,
                "signal": (
                    f"Revenue declining for {declining_quarters} consecutive years \u2014 "
                    f"YoY changes: {yoy_str}"
                ),
                "category": "revenue_trend",
                "field": "revenue_cr",
            })
        elif declining_quarters == 1:
            signals.append({
                "level": 1,
                "signal": (
                    f"Revenue declined {rev_yoy[-1]['pct_change']:+.1f}% in "
                    f"{rev_yoy[-1]['from_year']}→{rev_yoy[-1]['to_year']}"
                ),
                "category": "revenue_trend",
                "field": "revenue_cr",
            })

        # ── DSCR trend ────────────────────────────────────────────────────────
        dscr_now = latest.get("dscr")
        if dscr_now is not None:
            if dscr_now < 1.0:
                signals.append({
                    "level": 2,
                    "signal": (
                        f"DSCR {dscr_now:.2f} below 1.0 — company cannot service debt "
                        f"from operating income (RBI threshold: 1.25)"
                    ),
                    "category": "debt_serviceability",
                    "field": "dscr",
                })
            elif dscr_now < 1.25:
                signals.append({
                    "level": 1,
                    "signal": (
                        f"DSCR {dscr_now:.2f} below RBI recommended threshold of 1.25"
                    ),
                    "category": "debt_serviceability",
                    "field": "dscr",
                })

        dscr_yoy = yoy.get("dscr", [])
        if dscr_yoy and all(y["pct_change"] < 0 for y in dscr_yoy):
            dscr_yoy_str = ", ".join(
                f"{y['from_year']}\u2192{y['to_year']}: {y['pct_change']:+.1f}%"
                for y in dscr_yoy
            )
            signals.append({
                "level": 1,
                "signal": (
                    f"DSCR deteriorating consistently over {len(years)} years "
                    f"({dscr_yoy_str})"
                ),
                "category": "debt_serviceability",
                "field": "dscr",
            })

        # ── Profitability trend ───────────────────────────────────────────────
        np_now = latest.get("net_profit_cr")
        if np_now is not None and np_now < 0:
            signals.append({
                "level": 3,
                "signal": f"Net loss of ₹{abs(np_now):.2f} Cr in {latest_yr} — company is loss-making",
                "category": "profitability",
                "field": "net_profit_cr",
            })
        elif np_now is not None:
            np_yoy = yoy.get("net_profit_cr", [])
            if len(np_yoy) >= 2 and all(y["pct_change"] < 0 for y in np_yoy):
                signals.append({
                    "level": 1,
                    "signal": f"Net profit declining for {len(np_yoy)} consecutive years",
                    "category": "profitability",
                    "field": "net_profit_cr",
                })

        # ── Current ratio trend ───────────────────────────────────────────────
        cr_now = latest.get("current_ratio")
        if cr_now is not None and cr_now < 1.0:
            signals.append({
                "level": 2,
                "signal": (
                    f"Current ratio {cr_now:.2f} below 1.0 — current liabilities "
                    f"exceed current assets (liquidity stress)"
                ),
                "category": "liquidity",
                "field": "current_ratio",
            })
        elif cr_now is not None and cr_now < 1.33:
            signals.append({
                "level": 1,
                "signal": f"Current ratio {cr_now:.2f}, below RBI preferred minimum of 1.33",
                "category": "liquidity",
                "field": "current_ratio",
            })

        # ── Debt Equity deterioration ─────────────────────────────────────────
        de_now = latest.get("debt_to_equity")
        de_yoy = yoy.get("debt_to_equity", [])
        if de_now is not None and de_now > 3.0:
            signals.append({
                "level": 2,
                "signal": f"Debt-to-Equity ratio {de_now:.2f} — dangerously over-leveraged (threshold: 2:1)",
                "category": "leverage",
                "field": "debt_to_equity",
            })
        elif de_now is not None and de_now > 2.0:
            signals.append({
                "level": 1,
                "signal": f"Debt-to-Equity ratio {de_now:.2f} above recommended maximum of 2.0",
                "category": "leverage",
                "field": "debt_to_equity",
            })

        logger.info(f"Trend signals generated: {len(signals)} signals (years: {years})")
        return signals

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def extract_all(self, use_llm_fallback: bool = True) -> dict:
        """
        Runs the full extraction pipeline.

        Args:
            use_llm_fallback: If True, calls Gemini when regex fails (slower but more accurate).

        Returns:
            {
                "financials": {revenue_cr, ebitda_cr, ..., dscr, ...},
                "source_citations": {field: citation_string},
                "confidence": float,
            }
        """
        logger.info("Starting financial extraction...")

        # ── Step 1: Regex extraction for all fields ────────────────────────────
        all_fields = list(FIELD_PATTERNS.keys())
        for field in all_fields:
            val, citation = self.extract_field_regex(field)
            if val is not None:
                self._extracted[field] = val
                self._citations[field] = citation
                self._methods[field] = "regex"

        # ── Step 2: Table search for fields still missing ─────────────────────
        table_keywords = {
            "revenue_cr":           ["revenue", "turnover", "sales"],
            "ebitda_cr":            ["ebitda", "operating profit"],
            "net_profit_cr":        ["net profit", "profit after tax", "pat"],
            "total_assets_cr":      ["total assets"],
            "total_liabilities_cr": ["total liabilities"],
            "net_worth_cr":         ["net worth", "shareholders equity"],
            "_interest_expense_cr": ["finance cost", "interest"],
            "_depreciation_cr":     ["depreciation"],
            "_current_assets_cr":   ["current assets"],
            "_current_liabilities_cr": ["current liabilities"],
            "_total_debt_cr":       ["borrowings", "total debt"],
        }

        for field, keywords in table_keywords.items():
            if field not in self._extracted:
                val = self._search_tables(keywords)
                if val is not None:
                    self._extracted[field] = val
                    self._citations[field] = "Extracted from table in document"
                    self._methods[field] = "table"
                    logger.debug(f"[table] {field} = {val}")

        # ── Step 3: LLM fallback for remaining required fields ─────────────────
        if use_llm_fallback:
            # Only call LLM for fields that are truly needed
            llm_target_fields = all_fields  # attempt all for best coverage
            for field in llm_target_fields:
                if field not in self._extracted:
                    val, citation = self.extract_field_llm(field)
                    if val is not None:
                        self._extracted[field] = val
                        self._citations[field] = citation
                        self._methods[field] = "llm"

        # ── Step 4: Compute derived ratios ────────────────────────────────────
        ratios, ratio_citations = self.compute_ratios()

        # ── Step 5: Assemble final financials dict ────────────────────────────
        financials = {
            "revenue_cr":           self._extracted.get("revenue_cr", 0.0),
            "ebitda_cr":            self._extracted.get("ebitda_cr", 0.0),
            "net_profit_cr":        self._extracted.get("net_profit_cr", 0.0),
            "total_assets_cr":      self._extracted.get("total_assets_cr", 0.0),
            "total_liabilities_cr": self._extracted.get("total_liabilities_cr", 0.0),
            "net_worth_cr":         self._extracted.get("net_worth_cr", 0.0),
            "dscr":                 ratios.get("dscr", 1.0),
            "current_ratio":        ratios.get("current_ratio", 1.0),
            "debt_to_equity":       ratios.get("debt_to_equity", 1.5),
            "interest_coverage":    ratios.get("interest_coverage", 2.0),
        }

        # If net_worth wasn't extracted, compute from assets - liabilities
        if financials["net_worth_cr"] == 0.0:
            a = financials["total_assets_cr"]
            l = financials["total_liabilities_cr"]
            if a > 0 and l > 0:
                financials["net_worth_cr"] = round(a - l, 2)
                self._citations["net_worth_cr"] = "Computed: Total Assets − Total Liabilities"
                self._methods["net_worth_cr"] = "computed"

        # ── Step 6: Merge citations ───────────────────────────────────────────
        all_citations = {**self._citations, **ratio_citations}

        # Keep only CONTRACT 1 citation fields (clean output)
        contract_citation_fields = [
            "revenue_cr", "ebitda_cr", "net_profit_cr",
            "total_assets_cr", "total_liabilities_cr",
            "net_worth_cr", "dscr", "current_ratio",
            "debt_to_equity", "interest_coverage",
        ]
        source_citations = {k: all_citations.get(k, "Not found") for k in contract_citation_fields}

        # ── Feature 2: Structured citations (rich provenance) ─────────────────
        # For any field not reached by regex/llm, add a default-method citation
        for field in contract_citation_fields:
            if field not in self._citations_structured:
                val = financials.get(field, 0.0) or ratios.get(field, 0.0) or 0.0
                self._citations_structured[field] = self._make_citation(
                    val, field, None,
                    all_citations.get(field, "Not found — default value used"),
                    "default",
                )

        source_citations_structured = {
            k: self._citations_structured[k]
            for k in contract_citation_fields
            if k in self._citations_structured
        }

        confidence = self.confidence_score()

        logger.info(
            f"Extraction complete. "
            f"Confidence: {confidence:.2f}. "
            f"Methods: {dict((k, v) for k,v in self._methods.items() if not k.startswith('_'))}"
        )

        # ── Step 7: Multi-year trend analysis ────────────────────────────────
        multi_year = self.extract_multi_year()
        yoy        = self.compute_yoy_changes(multi_year)
        trend_sigs = self.generate_trend_signals(multi_year, yoy)

        return {
            "financials":                financials,
            "source_citations":          source_citations,          # plain strings (backward compat)
            "source_citations_structured": source_citations_structured,  # Feature 2: rich objects
            "confidence":                confidence,
            "multi_year_financials":     multi_year,
            "yoy_changes":               yoy,
            "trend_signals":             trend_sigs,
        }
