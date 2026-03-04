"""
document_pipeline.py — Module 1: Document Intelligence
========================================================
Master orchestrator for Module 1.

Takes a list of uploaded file paths, auto-routes each to the correct parser,
merges all outputs into a single DocumentReport (CONTRACT 1).

CONTRACT 1 output schema:
{
    "company_name":         str,
    "gstin":                str,
    "financials":           {revenue_cr, ebitda_cr, net_profit_cr, ...},
    "gst_analysis":         {mismatch_pct, mismatch_flag, ...},
    "bank_statement":       {avg_balance_cr, emi_outflow_monthly_cr, ...},
    "extraction_confidence": float,
    "source_citations":     {field: citation_string},
}

Usage:
    from modules.document_intelligence.document_pipeline import run_pipeline

    result = run_pipeline(
        uploaded_files=[
            "annual_report.pdf",
            "gstr3b_FY24.xlsx",
            "gstr2a_FY24.xlsx",
            "bank_statement.csv",
        ],
        company_name="Apex Textiles Pvt Ltd",
        gstin="27AAPCA5678H1Z2",
    )
"""

import os
import logging
from typing import Optional

from modules.document_intelligence.pdf_ingestor import PDFIngestor
from modules.document_intelligence.financial_extractor import FinancialExtractor
from modules.document_intelligence.gst_validator import GSTCrossValidator
from modules.document_intelligence.bank_parser import BankStatementParser
from modules.document_intelligence.ews_generator import EarlyWarningSignalGenerator
from modules.document_intelligence.mock_data import APEX_TEXTILES_DOC_REPORT

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# File Classifier
# ─────────────────────────────────────────────────────────────────────────────

class FileClassifier:
    """
    Classifies uploaded files into their document type based on
    filename patterns, extension, and keyword scanning.
    """

    ANNUAL_REPORT_KEYWORDS = [
        "annual", "report", "financial", "balance", "profit", "loss",
        "statement", "accounts", "p&l", "bs", "ar", "itr"
    ]
    GST_3B_KEYWORDS  = ["3b", "gstr3b", "gstr-3b", "3b_", "_3b", "3b.", "return"]
    GST_2A_KEYWORDS  = ["2a", "gstr2a", "gstr-2a", "2a_", "_2a", "2a.", "auto"]
    BANK_KEYWORDS    = ["bank", "statement", "account", "passbook", "ledger", "current", "saving", "ca", "ods"]
    LEGAL_KEYWORDS    = ["legal", "notice", "litigation", "court", "summon", "case"]
    SANCTION_KEYWORDS = ["sanction", "loan", "letter", "term", "limit", "bank", "proposal"]

    def classify(self, filepath: str) -> str:
        """
        Returns one of: 'annual_report' | 'gstr3b' | 'gstr2a' | 'bank_statement' | 'legal_notice' | 'sanction_letter' | 'unknown'
        """
        filename = os.path.basename(filepath).lower()
        ext = os.path.splitext(filename)[-1].lower()

        # GST files are always Excel or CSV
        if ext in [".xlsx", ".xls", ".csv"]:
            if any(kw in filename for kw in self.GST_3B_KEYWORDS):
                return "gstr3b"
            if any(kw in filename for kw in self.GST_2A_KEYWORDS):
                return "gstr2a"
            if any(kw in filename for kw in self.BANK_KEYWORDS):
                return "bank_statement"
            # Default for CSVs/Excel without known pattern → assume bank
            return "bank_statement"

        if ext == ".pdf":
            if any(kw in filename for kw in self.BANK_KEYWORDS):
                return "bank_statement"
            if any(kw in filename for kw in self.LEGAL_KEYWORDS):
                return "legal_notice"
            if any(kw in filename for kw in self.SANCTION_KEYWORDS):
                return "sanction_letter"
            # Default for PDFs → annual report / financial statement
            return "annual_report"

        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    uploaded_files: list[str],
    company_name: str = "Unknown Company",
    gstin: str = "",
    use_llm_fallback: bool = True,
    demo_mode: bool = False,
) -> dict:
    """
    End-to-end document intelligence pipeline.

    Routes each file → correct parser → merges into DocumentReport.

    Args:
        uploaded_files:   List of file paths (PDF, CSV, Excel)
        company_name:     Company name for the report header
        gstin:            GSTIN of the company
        use_llm_fallback: Enable Gemini fallback in FinancialExtractor
        demo_mode:        If True, bypass all parsing and return the Apex Textiles
                          demo scenario instantly (useful for hackathon demos)

    Returns:
        DocumentReport dict matching CONTRACT 1 exactly
    """
    logger.info(
        f"Pipeline start — company='{company_name}', "
        f"files={len(uploaded_files)}, demo_mode={demo_mode}"
    )

    # ── Feature 4: Demo Mode ────────────────────────────────────────────────────
    if demo_mode:
        logger.info("Demo mode active — returning Apex Textiles cached scenario")
        demo_report = dict(APEX_TEXTILES_DOC_REPORT)
        # Override company_name/gstin if caller supplied them
        if company_name and company_name != "Unknown Company":
            demo_report = {**demo_report, "company_name": company_name}
        if gstin:
            demo_report = {**demo_report, "gstin": gstin}
        return demo_report

    classifier = FileClassifier()

    # Categorize files
    annual_reports = []
    gstr3b_files   = []
    gstr2a_files   = []
    bank_files     = []
    legal_notice_files = []
    sanction_letter_files = []
    unknown_files  = []

    # Trend + citation data — populated if annual reports are processed
    multi_year_financials: dict = {}
    yoy_changes: dict = {}
    trend_signals: list = []
    source_citations_structured: dict = {}  # Feature 2: rich provenance objects
    early_warning_signals: list = []         # Feature 3: RBI EWS signals

    for fp in uploaded_files:
        if not os.path.exists(fp):
            logger.warning(f"File not found, skipping: {fp}")
            continue
        doc_type = classifier.classify(fp)
        logger.info(f"  {os.path.basename(fp)} → {doc_type}")

        if doc_type == "annual_report":
            annual_reports.append(fp)
        elif doc_type == "gstr3b":
            gstr3b_files.append(fp)
        elif doc_type == "gstr2a":
            gstr2a_files.append(fp)
        elif doc_type == "bank_statement":
            bank_files.append(fp)
        elif doc_type == "legal_notice":
            legal_notice_files.append(fp)
        elif doc_type == "sanction_letter":
            sanction_letter_files.append(fp)
        else:
            unknown_files.append(fp)

    if unknown_files:
        logger.warning(f"Unclassified files (skipped): {unknown_files}")

    # ── 1. Financial & Risk Extraction ─────────────────────────────────────────
    financials       = _default_financials()
    source_citations = {}
    fin_confidence   = 0.0
    qualitative_risks = []

    # Process Annual Reports, Legal Notices, and Sanction Letters
    target_extraction_files = annual_reports + legal_notice_files + sanction_letter_files
    
    if target_extraction_files:
        ingestor = PDFIngestor()
        combined_text  = {}
        combined_tables = []
        page_offset = 0

        for fp in target_extraction_files:
            try:
                ingest_result = ingestor.ingest(fp)
                for pg, text in ingest_result["raw_text"].items():
                    combined_text[pg + page_offset] = text
                combined_tables.extend(ingest_result["tables"])
                page_offset += ingest_result["page_count"]
            except Exception as e:
                logger.error(f"Ingest failed for {fp}: {e}")

        if combined_text:
            extractor = FinancialExtractor(combined_text, combined_tables)
            
            # Extract Financials (only if we have an annual report)
            if annual_reports:
                fin_result = extractor.extract_all(use_llm_fallback=use_llm_fallback)
                financials                    = fin_result["financials"]
                source_citations              = fin_result["source_citations"]
                source_citations_structured   = fin_result.get("source_citations_structured", {})
                fin_confidence                = fin_result["confidence"]
                multi_year_financials         = fin_result.get("multi_year_financials", {})
                yoy_changes                   = fin_result.get("yoy_changes", {})
                trend_signals                 = fin_result.get("trend_signals", [])
            
            # Extract Qualitative Risks (Pillar 1 requirement)
            for fp in target_extraction_files:
                doc_type = classifier.classify(fp)
                if doc_type in ["legal_notice", "sanction_letter", "annual_report"]:
                    risks = extractor.extract_unstructured_risks(doc_type=doc_type)
                    qualitative_risks.extend(risks)

            logger.info(f"Extraction done. confidence={fin_confidence:.2f}, risks={len(qualitative_risks)}")
    else:
        logger.warning("No relevant PDFs provided — using default financial values")

    # ── 2. GST Analysis ────────────────────────────────────────────────────────
    gst_analysis = _default_gst_analysis()

    if gstr3b_files and gstr2a_files:
        try:
            gst_validator = GSTCrossValidator()
            gst_validator.load_gstr3b(gstr3b_files[0])
            gst_validator.load_gstr2a(gstr2a_files[0])

            bank_credits_cr = financials.get("revenue_cr", 0.0)
            gst_result = gst_validator.validate(bank_credits_cr=bank_credits_cr)

            gst_analysis = {
                "mismatch_pct":           gst_result["mismatch_pct"],
                "mismatch_flag":          gst_result["mismatch_flag"],
                "circular_trading_flag":  gst_result["circular_trading_flag"],
                "revenue_inflation_flag": gst_result["revenue_inflation_flag"],
                "gst_score":              gst_result["gst_score"],
            }
            logger.info(f"GST analysis done. flag={gst_analysis['mismatch_flag']}, "
                        f"score={gst_analysis['gst_score']}/20")
        except Exception as e:
            logger.error(f"GST validation failed: {e}")
    else:
        if not gstr3b_files:
            logger.warning("No GSTR-3B file provided — using default GST analysis")
        if not gstr2a_files:
            logger.warning("No GSTR-2A file provided — using default GST analysis")

    # ── 3. Bank Statement ─────────────────────────────────────────────────────
    bank_statement = _default_bank_statement()

    if bank_files:
        try:
            bank_parser = BankStatementParser()
            bank_result = bank_parser.parse(bank_files[0])
            bank_statement = bank_result
            logger.info(f"Bank parsing done. avg_balance={bank_result['avg_balance_cr']:.3f} Cr")
        except Exception as e:
            logger.error(f"Bank statement parsing failed: {e}")
    else:
        logger.warning("No bank statement file provided — using default bank values")

    # ── 4. Compute overall confidence (weighted average) ──────────────────────
    has_fin  = 1 if annual_reports else 0
    has_gst  = 1 if (gstr3b_files and gstr2a_files) else 0
    has_bank = 1 if bank_files else 0
    completeness = (has_fin + has_gst + has_bank) / 3

    extraction_confidence = round(
        (fin_confidence * 0.5 + completeness * 0.5), 3
    )

    # ── 5. Generate Early Warning Signals (Feature 3) ─────────────────────────
    ews_gen = EarlyWarningSignalGenerator(
        financials=financials,
        gst_analysis=gst_analysis,
        bank_statement=bank_statement,
        trend_signals=trend_signals,
    )
    early_warning_signals = ews_gen.generate()

    # ── 6. Assemble final DocumentReport ──────────────────────────────────────
    low_confidence_fields = [
        k for k, v in source_citations_structured.items()
        if v.get("confidence", 1.0) < 0.75
    ]
    if not source_citations_structured:
        low_confidence_fields = list(_default_financials().keys())

    document_report = {
        "company_name":                   company_name,
        "gstin":                          gstin,
        "financials":                     financials,
        "gst_analysis":                   gst_analysis,
        "bank_statement":                 bank_statement,
        "extraction_confidence":          float(extraction_confidence),
        "source_citations":               source_citations,              # plain strings (backward compat)
        "source_citations_structured":    source_citations_structured,   # Feature 2: rich objects
        "early_warning_signals":          early_warning_signals,         # Feature 3: RBI EWS
        "low_confidence_fields":          low_confidence_fields,         # Feature 5: Review flags
        # ── Multi-year trend data (Feature 1) ──
        "multi_year_financials":          multi_year_financials,
        "yoy_changes":                    yoy_changes,
        "trend_signals":                  trend_signals,
        "qualitative_risks":              qualitative_risks,
    }

    logger.info(
        f"Pipeline complete — confidence={extraction_confidence:.2f}, "
        f"completeness: fin={has_fin}, gst={has_gst}, bank={has_bank}"
    )
    return document_report


# ─────────────────────────────────────────────────────────────────────────────
# Default fallback values (safe CONTRACT 1 compliant defaults)
# ─────────────────────────────────────────────────────────────────────────────

def _default_financials() -> dict:
    return {
        "revenue_cr":           0.0,
        "ebitda_cr":            0.0,
        "net_profit_cr":        0.0,
        "total_assets_cr":      0.0,
        "total_liabilities_cr": 0.0,
        "net_worth_cr":         0.0,
        "dscr":                 0.0,
        "current_ratio":        0.0,
        "debt_to_equity":       0.0,
        "interest_coverage":    0.0,
    }


def _default_gst_analysis() -> dict:
    return {
        "mismatch_pct":           0.0,
        "mismatch_flag":          "GREEN",
        "circular_trading_flag":  False,
        "revenue_inflation_flag": False,
        "gst_score":              20,
    }


def _default_bank_statement() -> dict:
    return {
        "avg_balance_cr":         0.0,
        "emi_outflow_monthly_cr": 0.0,
        "peak_balance_cr":        0.0,
        "regular_credits":        False,
        "month_on_month_volatility": 0.0,
        "stress_months_count":       0,
        "inward_outward_ratio_trend": [],
    }
