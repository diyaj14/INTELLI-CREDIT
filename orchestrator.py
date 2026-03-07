import os
import json
import sys

sys.path.append(os.path.abspath("."))

from modules.document_intelligence.document_pipeline import run_pipeline
from modules.research_agent.research_pipeline import run_research
from modules.credit_scoring.scorecard_model import (
    ScorecardModel,
    FinancialMetrics,
    GSTReport,
    ResearchReport,
    QualitativeNotes,
)

def _build_financial_metrics(fin):
    revenue = fin.get("revenue_cr") or 1.0
    ebitda  = fin.get("ebitda_cr", 0.0)
    profit  = fin.get("net_profit_cr", 0.0)
    assets  = fin.get("total_assets_cr") or 1.0
    return FinancialMetrics(
        current_ratio     = fin.get("current_ratio")     or None,
        debt_to_equity    = fin.get("debt_to_equity")    or None,
        interest_coverage = fin.get("interest_coverage") or None,
        net_profit_margin = (profit / revenue) if revenue else None,
        ebitda_margin     = (ebitda / revenue) if revenue else None,
        return_on_assets  = (profit / assets)  if assets  else None,
    )

def _build_gst_report(gst):
    gst_score  = gst.get("gst_score", 20)
    filing_pct = (gst_score / 20.0) * 100.0
    return GSTReport(
        filing_compliance_pct = filing_pct,
        revenue_mismatch_pct  = gst.get("mismatch_pct", 0.0),
        notices_count         = 1 if gst.get("mismatch_flag") == "RED" else 0,
    )

def _build_research_report(research):
    news = research.get("news_sentiment", {})
    if isinstance(news, dict):
        sentiment = news.get("score", 0.0)
        neg_count = len(news.get("headlines", []))
    else:
        sentiment = 0.0
        neg_count = 0
    return ResearchReport(
        news_sentiment_score  = sentiment,
        sector_headwind_score = 0.3,
        negative_news_count   = neg_count,
        regulatory_risk_flag  = research.get("mca_data", {}).get("struck_off_subsidiaries", 0) > 0,
        peer_percentile       = 50.0,
    )

def _build_qualitative_notes(research):
    litigation = research.get("litigation", {})
    return QualitativeNotes(
        litigation_cases        = len(litigation.get("cases", [])),
        mca_active_charges      = research.get("mca_data", {}).get("charges_outstanding", 0),
        director_disqualified   = research.get("mca_data", {}).get("director_disqualified", False),
        officer_override_score  = 0.0,
        officer_override_reason = "",
    )

def orchestrate(uploaded_files, company_name=None, gstin=None,
                promoter_names=None, primary_insights=None,
                officer_override_score=0.0, officer_override_reason=""):

    print("--- Running Module 1: Document Intelligence ---")
    doc_report = run_pipeline(
        uploaded_files=uploaded_files,
        company_name=company_name or "Unknown Company",
        gstin=gstin or "",
        demo_mode=(not uploaded_files and not company_name)
    )

    extracted_company = doc_report.get("company_name") or company_name or "Unknown Company"
    if not promoter_names and "Apex Textiles" in extracted_company:
        promoter_names = ["Ramesh Gupta"]
    print(f"Final Company Name for Research: {extracted_company}")

    print("\n--- Running Module 2: Research Agent ---")
    research_report = run_research(
        company_name=extracted_company,
        promoter_names=promoter_names or [],
        primary_insights=primary_insights or "",
        demo_mode=(not uploaded_files and "Apex Textiles" in extracted_company)
    )

    print("\n--- Running Module 3: Scoring Engine ---")
    fm   = _build_financial_metrics(doc_report.get("financials", {}))
    gst  = _build_gst_report(doc_report.get("gst_analysis", {}))
    res  = _build_research_report(research_report)
    qual = _build_qualitative_notes(research_report)
    qual.officer_override_score  = officer_override_score
    qual.officer_override_reason = officer_override_reason

    score_report = ScorecardModel().score(fm, gst, res, qual)
    print(score_report.summary)

    return {
        "document_intelligence": doc_report,
        "research_agent":        research_report,
        "credit_score": {
            "total":    score_report.total_score,
            "decision": score_report.decision,
            "breakdown": {
                "financial_health":  score_report.breakdown.financial_health,
                "gst_compliance":    score_report.breakdown.gst_compliance,
                "promoter_quality":  score_report.breakdown.promoter_quality,
                "external_intel":    score_report.breakdown.external_intel,
                "officer_override":  score_report.breakdown.officer_override,
            },
            "flags":   score_report.flags,
            "summary": score_report.summary,
        }
    }

if __name__ == "__main__":
    result = orchestrate([], company_name="Apex Textiles")
    print("\n--- Final Credit Score ---")
    print(json.dumps(result["credit_score"], indent=2))
