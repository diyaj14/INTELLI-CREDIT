
import pdfplumber
import os
import logging

logger = logging.getLogger(__name__)

class DocumentIngestor:
    """
    Parses PDF files into raw text and tables using pdfplumber.
    """
    


    def ingest(self, file_path: str, progress_callback=None) -> dict:
        """
        Extracts content from a PDF with semantic tagging for speed.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        results = {"text": {}, "tables": [], "page_count": 0, "financial_pages": []}
        fin_keywords = ["balance sheet", "profit & loss", "profit and loss", "financial statement", "p&l", "cash flow", "income statement"]

        try:
            with pdfplumber.open(file_path) as pdf:
                total = len(pdf.pages)
                results["page_count"] = total
                


                for i, page in enumerate(pdf.pages):
                    try:
                        if progress_callback:
                            progress_callback(f"Scanning Page {i+1}/{total}...", int(((i+1)/total)*100))
                        
                        raw_text = page.extract_text() or ""
                        
                        # Convert tables to text for LLM visibility
                        table_text = ""
                        tables = page.extract_tables()
                        for table in tables:
                            if table:
                                cleaned_rows = [" | ".join([str(cell).replace('\n', ' ') for cell in row if cell is not None]) for row in table if any(row)]
                                table_text += "\n[TABLE_START]\n" + "\n".join(cleaned_rows) + "\n[TABLE_END]\n"
                        
                        combined_text = raw_text + "\n" + table_text
                        results["text"][i + 1] = combined_text
                        
                        # Tag financial pages for speed
                        low_text = combined_text.lower()
                        if any(kw in low_text for kw in fin_keywords):
                            results["financial_pages"].append(i + 1)
                        
                        # Keep raw tables as well
                        for table in tables:
                            if table:
                                cleaned_table = [row for row in table if any(row)]
                                if cleaned_table:
                                    results["tables"].append(cleaned_table)
                    except Exception as page_err:

                        logger.warning(f"Skipping page {i+1} due to error: {page_err}")
                        continue

            
            return results



            
        except Exception as e:
            logger.error(f"Error ingesting PDF {file_path}: {e}")
            raise e
