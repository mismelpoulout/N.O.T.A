# backend/core/llm_client.py
import os
import httpx
import asyncio

class LLMClient:
    def __init__(self):
        # Defaults seguros para dev (Ollama OpenAI-compatible)
        base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        model = os.getenv("LLM_MODEL", "llama3.2:3b-instruct")
        key   = os.getenv("LLM_API_KEY", "ollama")

        self.base_url = base
        self.model = model
        self.api_key = key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=60,
        )

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
            "stream": False,
        }
        r = await self._client.post("/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()