
import os
import json
import sys

# Ensure root is in path
sys.path.append(os.path.abspath("."))

from modules.document_intelligence.document_pipeline import run_pipeline
from modules.research_agent.research_pipeline import run_research

def orchestrate(uploaded_files, company_name=None, gstin=None, promoter_names=None, primary_insights=None):
    """
    Connects Module 1 (Data Ingestor) and Research Agent.
    """
    print(f"--- Running Module 1: Document Intelligence ---")
    doc_report = run_pipeline(
        uploaded_files=uploaded_files,
        company_name=company_name or "Unknown Company",
        gstin=gstin or "",
        demo_mode=(not uploaded_files and not company_name) # Run demo if no files AND no name
    )
    
    # Use extracted name if user didn't provide one
    extracted_company = doc_report.get("company_name") or company_name or "Unknown Company"
    if extracted_company == "Unknown Company" and "Apex Textiles" in doc_report.get("company_name", ""):
         extracted_company = "Apex Textiles Pvt Ltd"
         
    print(f"Final Company Name for Research: {extracted_company}")
    
    # Extract potential promoters if found in financials or metadata
    if not promoter_names and "Apex Textiles" in extracted_company:
        promoter_names = ["Ramesh Gupta"]
    
    print(f"\n--- Running Module 2: Research Agent ---")
    research_report = run_research(
        company_name=extracted_company,
        promoter_names=promoter_names or [],
        primary_insights=primary_insights or "",
        demo_mode=(not uploaded_files and extracted_company == "Apex Textiles Pvt Ltd")
    )
    
    return {
        "document_intelligence": doc_report,
        "research_agent": research_report
    }

if __name__ == "__main__":
    # Test with Apex Textiles (Demo Mode)
    result = orchestrate([], company_name="Apex Textiles")
    print(json.dumps(result, indent=2))
