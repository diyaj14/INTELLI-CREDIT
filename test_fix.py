
import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add current dir to path
sys.path.append(os.path.abspath("."))

from modules.document_intelligence.document_pipeline import run_pipeline

def test_pipeline():
    file_path = r"e:\itellicredit-final\INTELLI-CREDIT\sample-cam.pdf"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"--- Running Pipeline for {os.path.basename(file_path)} ---")
    result = run_pipeline(
        uploaded_files=[file_path],
        company_name="Unknown Company",
        use_llm_fallback=True
    )

    print("\n--- Pipeline Result ---")
    print(f"Company Name: {result.get('company_name')}")
    print(f"Confidence: {result.get('extraction_confidence')}")
    print(f"Revenue CR: {result.get('financials', {}).get('revenue_cr')}")
    print(f"Risks found: {len(result.get('qualitative_risks', []))}")
    print(f"EWS signals: {len(result.get('early_warning_signals', []))}")

if __name__ == "__main__":
    test_pipeline()
