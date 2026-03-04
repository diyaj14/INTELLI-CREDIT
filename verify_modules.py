import json
from modules.document_intelligence.document_pipeline import run_pipeline
from modules.research_agent.research_pipeline import run_research

def verify_modules():
    print("--- Verifying Module 1 (Document Intelligence) ---")
    doc_report = run_pipeline(uploaded_files=[], company_name="Apex Textiles Pvt Ltd", demo_mode=True)
    print(f"Module 1 Demo Report Generated for: {doc_report['company_name']}")
    print(f"Extraction Confidence: {doc_report['extraction_confidence']}")
    
    print("\n--- Verifying Module 2 (Research Agent) ---")
    research_report = run_research(company_name="Apex Textiles Pvt Ltd", promoter_names=[], demo_mode=True)
    print(f"Module 2 Report Generated for: {research_report['company_name']}")
    print(f"Litigation Found: {research_report['litigation']['found']}")
    
    print("\n✅ Both Modules are responding correctly.")

if __name__ == "__main__":
    verify_modules()
