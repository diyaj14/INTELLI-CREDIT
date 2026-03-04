import os
import requests
import logging
from typing import List, Dict
from ddgs import DDGS

logger = logging.getLogger(__name__)

class NewsAggregator:
    """
    Multi-engine news aggregator (Tavily + DuckDuckGo) for high accuracy.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com/search"

    def fetch_news(self, company_name: str, sector: str = None, promoters: List[str] = []) -> dict:
        """
        Ultra-Deep Intelligence Fetch: Aggregates across multiple engines (Tavily + DDG).
        """
        logger.info(f"🚀 Performing MULTI-SOURCE search for: {company_name}")
        
        # 1. Tavily Search (Deep AI-optimized search)
        tavily_results = []
        sector_summary = "Synthesizing sector insights..."
        
        if self.api_key:
            try:
                search_categories = {
                    "financial_risk": f"balance sheet analysis, debt news, and credit rating of {company_name}",
                    "litigation_risk": f"court cases, legal disputes, and regulatory notices for {company_name} and promoters {', '.join(promoters)}",
                    "sector_headwinds": f"current challenges, new RBI/SEBI regulations, and headwinds in {sector if sector else 'relevant'} industry India 2024",
                    "promoter_integrity": f"news about promoters {', '.join(promoters)} reputation and past business failures",
                    "social_sentiment": f"site:reddit.com OR site:quora.com {company_name} reviews, fraud, or red flags"
                }
                
                for category, query in search_categories.items():
                    payload = {
                        "api_key": self.api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": 5,
                        "include_answer": category == "sector_headwinds"
                    }
                    response = requests.post(self.base_url, json=payload)
                    if response.ok:
                        data = response.json()
                        for res in data.get("results", []):
                            res["category"] = category
                            res["source"] = "Tavily"
                        tavily_results.extend(data.get("results", []))
                        if category == "sector_headwinds":
                            sector_summary = data.get("answer", sector_summary)
            except Exception as e:
                logger.error(f"Tavily search error: {e}")

        # 2. DuckDuckGo Search (Broad news coverage)
        ddg_results = []
        try:
            with DDGS() as ddgs:
                ddg_query = f"{company_name} promoters {', '.join(promoters)} legal news fraud default"
                for r in ddgs.text(ddg_query, max_results=10):
                    ddg_results.append({
                        "title": r.get('title'),
                        "url": r.get('href'),
                        "content": r.get('body'),
                        "category": "general_web_search",
                        "source": "DuckDuckGo"
                    })
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")

        # 3. Merge and De-duplicate
        all_results = tavily_results + ddg_results
        unique_results = {res['url']: res for res in all_results}.values()
        headlines = [res.get("title") for res in unique_results]
        
        logger.info(f"Merged {len(unique_results)} intelligence items from Tavily and DDG.")

        return {
            "score": 0.1, 
            "headlines": list(set(headlines)),
            "sector_headwinds": sector_summary,
            "deep_intelligence": list(unique_results)
        }

if __name__ == "__main__":
    # Test with a known company if key exists
    aggregator = NewsAggregator()
    print(aggregator.fetch_news("Reliance Industries"))
