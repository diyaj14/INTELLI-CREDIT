
from .ingestor import DocumentIngestor
from .extractor import OllamaFinancialExtractor
import os
import logging

logger = logging.getLogger(__name__)

class DocumentPipeline:

    def __init__(self, provider=None):
        self.ingestor = DocumentIngestor()
        self.extractor = OllamaFinancialExtractor(provider=provider)



    def run(self, file_paths: list, progress_callback=None) -> dict:
        """
        Runs the full Pillar 1 pipeline on a list of files.
        """
        if not file_paths:
            return self._get_empty_result()

        primary_file = file_paths[0]
        
        try:
            # 1. Ingest
            ingest_data = self.ingestor.ingest(primary_file, progress_callback=progress_callback)

            all_text = " ".join(ingest_data["text"].values())
            

            # Combine more pages for LLM context in large reports
            fin_pages = ingest_data.get("financial_pages", [])
            if fin_pages:
                # Upgraded: Take top 30 relevant pages instead of 10
                relevant_text = " ".join([ingest_data["text"][p] for p in fin_pages[:30]])
                if progress_callback: progress_callback("Deep Extraction: Scanning Financial Core (30 Pages)...", 85)
            else:
                # Upgraded: Take top 30 pages instead of 15
                relevant_text = " ".join([text for i, text in ingest_data["text"].items() if i <= 30])
                if progress_callback: progress_callback("Deep Extraction: Broad Scan (30 Pages)...", 80)

            

            # 2. Extract Financials
            financials = self.extractor.extract_financials(relevant_text)
            
            # 3. Multi-year Trends
            multi_year = self.extractor.extract_multi_year(relevant_text)
            
            # 4. Extract Risks
            risks = self.extractor.extract_risks(relevant_text)

            

            # 5. Simple Trend Logic
            def _to_f(v):
                try: return float(v) if v is not None else 0.0
                except: return 0.0

            revenue_growth = 0.0
            curr_rev = _to_f(multi_year.get("current_year", {}).get("revenue_cr"))
            prev_rev = _to_f(multi_year.get("previous_year", {}).get("revenue_cr"))
            if curr_rev and prev_rev:
                revenue_growth = round(((curr_rev - prev_rev) / prev_rev) * 100, 2)


            return {
                "company_name": financials.get("company_name", "Unknown"),
                "financials": financials,
                "multi_year": multi_year,
                "trends": {
                    "revenue_growth_pct": revenue_growth
                },
                "qualitative_risks": risks,
                "extraction_confidence": 0.85,
                "page_count": ingest_data["page_count"]
            }

            
        except Exception as e:
            logger.error(f"Pillar 1 Pipeline failed: {e}")
            return self._get_empty_result()

    def _get_empty_result(self):
        return {
            "company_name": "Unknown",
            "financials": {},
            "qualitative_risks": [],
            "extraction_confidence": 0.0
        }
