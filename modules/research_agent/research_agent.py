from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
import os
import json
import logging
from .mca_scraper import MCAScraper
from .ecourt_searcher import ECourtSearcher
from .news_aggregator import NewsAggregator

# We don't import from 'langchain' to avoid the 1.2.10 conflict
logger = logging.getLogger(__name__)

class ResearchAgent:
    """
    The "Digital Credit Manager" Custom ReAct Agent.
    Does NOT depend on the conflicting 'langchain' top-level package.
    Uses 'langchain-core' and 'langchain-google-genai' directly.
    """
    
    def __init__(self, gemini_model: str = "gemini-2.0-flash", groq_model: str = "llama-3.3-70b-versatile"):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
        self.gemini_model = gemini_model
        self.groq_model = groq_model
        
        # Initialize component tools
        self.mca = MCAScraper()
        self.ecourts = ECourtSearcher()
        self.news = NewsAggregator()
        
        # Lazy initialization of LLMs
        self._llm = None
        self._fallback_llm = None
    def _call_llm(self, messages: list, temperature: float = 0, timeout: int = 30) -> str:
        """
        Helper to call LLMs with fallback logic: Gemini -> Groq -> OpenRouter.
        """
        # 1. Try Gemini
        if self.google_api_key:
            try:
                if not self._llm:
                    self._llm = ChatGoogleGenerativeAI(model=self.gemini_model, google_api_key=self.google_api_key, temperature=temperature, timeout=timeout)
                resp = self._llm.invoke(messages)
                return resp.content
            except Exception as e:
                logger.warning(f"Gemini call failed: {e}. Trying Groq...")

        # 2. Try Groq
        if self.groq_api_key:
            try:
                if not self._fallback_llm:
                    self._fallback_llm = ChatGroq(model=self.groq_model, groq_api_key=self.groq_api_key, temperature=temperature, timeout=timeout)
                resp = self._fallback_llm.invoke(messages)
                return resp.content
            except Exception as e:
                logger.warning(f"Groq call failed: {e}. Trying OpenRouter...")

        # 3. Try OpenRouter
        or_api_key = os.getenv("OPENROUTER_API_KEY")
        if or_api_key:
            try:
                from langchain_openai import ChatOpenAI
                or_llm = ChatOpenAI(
                    model="deepseek/deepseek-chat",
                    openai_api_key=or_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=temperature,
                    timeout=timeout + 15,
                    max_tokens=1000
                )
                resp = or_llm.invoke(messages)
                return resp.content
            except Exception as e:
                logger.error(f"OpenRouter call failed: {e}")
                raise e

        raise Exception("All LLM providers failed or no API keys configured.")

    def run(self, company_name: str, promoter_names: list, primary_insights: str = "", image_path: str = None) -> str:
        """
        Runs a simplified but robust agentic flow to synthesize a summary.
        """
        # 1.0 Auto-Promoter Discovery (If list is empty)
        if not promoter_names:
            logger.info(f"🕵️ No promoters provided. Auto-discovering for {company_name}...")
            discovery_data = self.news.fetch_news(f"founders and key promoters of {company_name}")
            discovery_prompt = (
                f"Based on these search results for '{company_name}', list the top 2-3 key promoters or founders. "
                f"Return ONLY a comma-separated list of names. Data: {json.dumps(discovery_data.get('headlines', []))}"
            )
            try:
                discovery_resp = self._call_llm([HumanMessage(content=discovery_prompt)])
                promoter_names = [name.strip() for name in discovery_resp.split(",")]
                logger.info(f"✅ Auto-discovered promoters: {', '.join(promoter_names)}")
            except Exception as e:
                logger.error(f"Auto-discovery failed: {e}")
                promoter_names = ["Unknown"]

        # STEP 1: Deep Context Gathering
        # 1.1 Search for 'Contagion Risk'
        contagion_data = self.news.fetch_news(company_name=f"{company_name} promoters", promoters=promoter_names)
        
        # 1.2 Gather structured data
        mca_data = self.mca.lookup_company(company_name)
        litigation_data = self.ecourts.search_litigation(company_name)
        news_data = self.news.fetch_news(company_name, promoters=promoter_names)

        # 1.3 Vision Analysis
        vision_insight = ""
        if image_path and os.path.exists(image_path) and self.google_api_key:
            try:
                # Vision usually requires Gemini specifically in this implementation
                vision_prompt = "You are a Credit Officer. Analyze this site visit photo. Describe machinery age, activity level, and any safety/red flags."
                # We use a fresh one for vision as it might need a different model/config
                vision_llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=self.google_api_key)
                vision_resp = vision_llm.invoke([
                    HumanMessage(content=[
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": image_path}
                    ])
                ])
                vision_insight = f"\n[VISION ANALYSIS]: {vision_resp.content}"
            except Exception as e:
                logger.error(f"Vision analysis failed: {e}")
                vision_insight = f"\n[VISION]: Error analyzing image."

        # STEP 2: Final Synthesis Prompt
        prompt = (
            f"You are the 'Digital Credit Manager' for Intelli-Credit.\n"
            f"Synthesize the research for '{company_name}' (Promoters: {', '.join(promoter_names)}):\n\n"
            f"MCA DATA: {json.dumps(mca_data)}\n"
            f"LITIGATION DATA (Deep-Dive): {json.dumps(litigation_data)}\n"
            f"CONTAGION RISK (Sister Companies): {json.dumps(contagion_data)}\n"
            f"SECONDARY RESEARCH (Social/Financial): {json.dumps(news_data)}\n"
            f"PRIMARY INSIGHTS (Officer Notes): {primary_insights}\n"
            f"{vision_insight}\n\n"
            "Task: Write a High-Level Credit Memo. "
            "1. CONTAGION: Evaluate if sibling companies pose a threat. "
            "2. CHARACTER: Differentiate between minor and major litigation. "
            "3. VISION: Incorporate factory/site observations into the capacity score. "
            "Be professional, concise, and highlight 'Decision-Critical' facts."
        )

        try:
            return self._call_llm([HumanMessage(content=prompt)])
        except Exception as e:
            return f"Error during AI analysis: All providers failed. {str(e)}"

if __name__ == "__main__":
    pass
