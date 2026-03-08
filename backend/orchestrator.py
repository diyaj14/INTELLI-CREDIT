
import os
import sys
import logging

# Add root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.document_intelligence.pipeline import DocumentPipeline
from modules.research_agent.pipeline import ResearchPipeline
from modules.credit_scoring.scorecard import Scorecard

from modules.credit_scoring.recommendation import RecommendationEngine

from modules.report_generator.pdf_generator import PDFGenerator
from modules.research_agent.hybrid_merger import HybridMerger

logger = logging.getLogger(__name__)



def orchestrate(uploaded_files, company_name=None, demo_mode=False, progress_callback=None, **kwargs):
    """
    Unified entry point for the Intelli-Credit appraisal process.
    """
    def log_progress(msg, prog):
        if progress_callback: progress_callback(msg, prog)
        logger.info(f"PROGRESS: {msg} ({prog}%)")

    log_progress("Initializing Pipeline", 5)
    
    # 1. Module 1: Document Intelligence (PDF Extraction)
    doc_pipeline = DocumentPipeline(provider=kwargs.get("llm_provider"))
    if uploaded_files:
        log_progress("Module 1: Deep Extracting PDF Data", 15)
        doc_intel = doc_pipeline.run(uploaded_files, progress_callback=progress_callback)
    else:
        # Mock data for demo/empty state
        doc_intel = {
            "company_name": company_name or "Demo Corp",
            "financials": {
                "revenue_cr": 125.0, "ebitda_cr": 18.5, "net_profit_cr": 8.2,
                "current_ratio": 1.4, "debt_to_equity": 0.8, "interest_coverage": 3.1
            },
            "qualitative_risks": [{"category": "Market", "risk": "High competition", "impact": "Medium"}],
            "extraction_confidence": 1.0
        }
    
    target_name = company_name or doc_intel.get("company_name", "Unknown Company")
    
    # 2. Module 2: Research Agent (Web & AI Search)
    log_progress("Module 2: Initiating Web Research & Sentiment Analysis", 60)
    research_pipeline = ResearchPipeline()
    research_data = research_pipeline.run(target_name)
    
    # 3. Hybrid Fusion: Merge PDF + Web Data
    log_progress("Hybrid Fusion: Cross-Verifying Data Sources", 80)
    merger = HybridMerger()
    doc_intel = merger.merge(doc_intel, research_data)

    # 4. Module 3: Decision & Scoring Engine
    log_progress("Module 3: Computing Smart Score & Final Decision", 90)
    scorecard = Scorecard()
    score_report = scorecard.compute(doc_intel, research_data)
    
    # Add fusion flags to scoring flags if any
    if "fusion_flags" in doc_intel:
        score_report["flags"] = (score_report.get("flags", []) + 
                                doc_intel["fusion_flags"] + 
                                doc_intel.get("discrepancies", []))

    rec_engine = RecommendationEngine()
    recommendation = rec_engine.suggest(score_report, doc_intel.get("financials", {}))

    # 5. Generate PDF Report
    log_progress("Finalizing: Generating PDF Credit Memo", 98)

    pdf_gen = PDFGenerator()
    full_data = {
        "document_intelligence": doc_intel,
        "research_agent": research_data,
        "scoring_model": {
            "overall_score": score_report["overall_score"],
            "decision": score_report["decision"],
            "breakdown": score_report["breakdown"],
            "detailed_scores": score_report.get("detailed_scores", {}),
            "flags": score_report.get("flags", [])
        },
        "loan_recommendation": recommendation
    }
    pdf_filename = pdf_gen.generate(full_data)

    
    return {
        "document_intelligence": doc_intel,
        "research_agent": research_data,
        "scoring_model": full_data["scoring_model"],
        "loan_recommendation": recommendation,
        "pdf_report_path": pdf_filename
    }


