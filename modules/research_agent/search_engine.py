
import os
import logging
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SearchEngine:
    """
    Handles web searching via Tavily.
    """
    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        self.client = TavilyClient(api_key=api_key) if api_key else None

    def search_company(self, company_name: str) -> dict:
        """
        Searches for news, MCA records, and litigation.
        """
        if not self.client:
            logger.warning("Tavily API key not found. Returning empty results.")
            return {"headlines": [], "mca_status": "Unknown", "litigation": "No data"}

        try:
            # 1. News Search
            query = f"{company_name} news financial performance India"
            news_result = self.client.search(query=query, search_depth="advanced")
            headlines = [r['title'] for r in news_result.get('results', [])[:5]]
            
            # 2. Litigation/Regulatory Check
            query_reg = f"{company_name} court cases legal disputes MCA portal"
            reg_result = self.client.search(query=query_reg, search_depth="basic")
            found_litigation = any("court" in r['content'].lower() or "dispute" in r['content'].lower() for r in reg_result.get('results', []))
            
            return {
                "headlines": headlines,
                "mca_status": "Active (Assumed)",
                "litigation_found": found_litigation,
                "raw_context": news_result.get('results', [])
            }
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"headlines": [], "mca_status": "Error", "litigation_found": False}

    def search_financials(self, company_name: str) -> str:
        """
        Targeted search for financial metrics.
        """
        if not self.client: return ""
        try:
            query = f"{company_name} financial results 2024 revenue net profit EBITDA crores lakhs"
            res = self.client.search(query=query, search_depth="advanced")
            # Return combined content for LLM extraction
            return "\n\n".join([r['content'] for r in res.get('results', [])])
        except Exception as e:
            logger.error(f"Financial search failed: {e}")
            return ""
