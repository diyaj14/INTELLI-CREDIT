import json
import logging
import os
import re

from .search_engine import SearchEngine
from ..llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

class ResearchPipeline:
    def __init__(self):
        self.search_engine = SearchEngine()
        self.gateway = LLMGateway()



    def run(self, company_name: str) -> dict:
        """
        Runs the full Pillar 2 Research pipeline with cascading fallback.
        Now includes deep web financial extraction for cross-verification.
        """
        # 1. Search Web for News, Sentiment & Financials
        search_data = self.search_engine.search_company(company_name)
        
        # 2. Get Sentiment Score (Refined for Credit Risk)
        # Use titles AND snippets for better context
        headlines_str = "\n".join([f"- {r.get('title')}: {r.get('content')[:150]}..." for r in search_data.get("raw_context", [])])
        
        sentiment_prompt = f"""
        Strictly analyze the Credit Sentiment for {company_name} based on these headlines and snippets.
        Focus on: Debt stability, defaults, regulatory issues, and financial health.
        Avoid being overly optimistic. 0.0 = Default Risk/Fraud, 0.5 = Stable/Neutral, 1.0 = Exceptional Growth.
        
        Evidence:
        {headlines_str}
        
        Return ONLY a JSON object: {{"score": float, "reasoning": "short string"}}
        """
        
        sentiment_resp = self.gateway.ask(sentiment_prompt, require_json=True)
        try:
            clean_json = re.sub(r'```json|```', '', sentiment_resp).strip()
            sent_data = json.loads(clean_json)
            sentiment_score = float(sent_data.get("score", 0.5))
            # Cap at 0.95 to avoid constant "10/10" unless absolutely perfect
            if sentiment_score > 0.95: sentiment_score = 0.9
        except:
            sentiment_score = 0.5

        # 3. Extract Financials from Web
        print(f"DEBUG: Scouring web for {company_name} financial data...")
        raw_fin_context = self.search_engine.search_financials(company_name)
        web_fin_data = {}
        if raw_fin_context:
            fin_prompt = f"""
            Extract 2024 financial metrics for {company_name} from these web snippets.
            Convert values to CRORES. Return EXCLUSIVELY JSON.
            Fields: revenue_cr, net_profit_cr, ebitda_cr.
            
            Text:
            {raw_fin_context[:8000]}
            
            JSON:
            """
            web_fin_resp = self.gateway.ask(fin_prompt, require_json=True)
            try:
                clean_json = re.sub(r'```json|```', '', web_fin_resp).strip()
                web_fin_data = json.loads(clean_json)
            except:
                logger.warning("Failed to extract financials from web snippets.")

        # 4. Synthesize Summary (Balanced)
        summary_prompt = f"""
        Provide a balanced 3-sentence credit summary for {company_name} based on the news.
        Mention both positives and potential concerns/risks.
        News: {headlines_str[:2000]}
        """
        summary = self.gateway.ask(summary_prompt)
        
        return {
            "company_name": company_name,
            "news_headlines": search_data["headlines"],
            "sentiment_score": sentiment_score,
            "web_financials": web_fin_data, 
            "mca_data": {"status": search_data["mca_status"]},
            "litigation": {"found": search_data["litigation_found"]},
            "agent_summary": summary
        }



