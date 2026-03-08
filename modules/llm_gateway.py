
import os
import json
import logging
import requests
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMGateway:
    """
    High-availability LLM interface with cascading fallback:
    Gemini -> Groq -> OpenRouter -> Ollama
    """
    
    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
        
    def ask(self, prompt: str, require_json: bool = False) -> str:
        """
        Main entry point for LLM requests.
        Cycles through providers until one succeeds.
        """
        
        # 1. Try Gemini (Flash)
        try:
            res = self._call_gemini(prompt, "gemini-1.5-flash")
            if res: return res
        except Exception as e:
            logger.warning(f"Fallback: Gemini Flash failed -> {e}")

        # 2. Try Groq (Llama 3 70B)
        try:
            res = self._call_groq(prompt, "llama3-70b-8192", require_json)
            if res: return res
        except Exception as e:
            logger.warning(f"Fallback: Groq failed -> {e}")

        # 3. Try OpenRouter (Gemini Flash as backup)
        try:
            res = self._call_openrouter(prompt, "google/gemini-flash-1.5")
            if res: return res
        except Exception as e:
            logger.warning(f"Fallback: OpenRouter failed -> {e}")

        # 4. Final Fail-Safe: Local Ollama
        logger.info(f"Falling back to Local Ollama ({self.ollama_model})")
        return self._call_ollama(prompt, require_json)

    def _call_gemini(self, prompt: str, model: str) -> Optional[str]:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: return None
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()['candidates'][0]['content']['parts'][0]['text']
        return None

    def _call_groq(self, prompt: str, model: str, require_json: bool) -> Optional[str]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key: return None
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        if require_json:
            payload["response_format"] = {"type": "json_object"}
            
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
        return None

    def _call_openrouter(self, prompt: str, model: str) -> Optional[str]:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key: return None
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:8001",
            "X-Title": "Intelli-Credit",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
        return None

    def _call_ollama(self, prompt: str, require_json: bool) -> str:
        try:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False
            }
            if require_json:
                payload["format"] = "json"
                
            resp = requests.post(url, json=payload, timeout=180)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return "Ollama error."
        except Exception as e:
            logger.error(f"Ollama critical failure: {e}")
            return "All models failed."
