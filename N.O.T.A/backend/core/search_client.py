# backend/core/search_client.py
from __future__ import annotations
from typing import List, Dict, Any
import os
import httpx

class SearchClient:
    def __init__(self, engine: str, client):
        self.engine = engine
        self._client = client

    @classmethod
    def from_env(cls, cfg: Dict[str, str] | os._Environ = os.environ) -> "SearchClient":
        engine = (cfg.get("SEARCH_ENGINE") or "google").strip().lower()
        if engine == "google":
            key = cfg.get("GOOGLE_API_KEY")
            cx  = cfg.get("GOOGLE_CX")
            return cls("google", GoogleCSEClient(key=key, cx=cx))
        elif engine == "bing":
            key = cfg.get("BING_KEY")
            ep  = cfg.get("BING_ENDPOINT") or "https://api.bing.microsoft.com/v7.0/search"
            mkt = cfg.get("BING_MKT", "es-CL")
            return cls("bing", BingClient(key=key, endpoint=ep, market=mkt))
        else:
            # “vacío”: siempre retorna []
            return cls("none", NullSearchClient())

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        return await self._client.search(query, count=count)


class NullSearchClient:
    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        return []


class GoogleCSEClient:
    def __init__(self, key: str | None, cx: str | None, endpoint: str | None = None, timeout_s: int = 10):
        self.key = key
        self.cx = cx
        self.endpoint = endpoint or "https://www.googleapis.com/customsearch/v1"
        self.timeout = timeout_s

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        if not self.key or not self.cx:
            return []
        params = {"key": self.key, "cx": self.cx, "q": query, "num": min(count, 10)}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.endpoint, params=params)
            r.raise_for_status()
            j = r.json()
            items = j.get("items", []) or []
            results = []
            for it in items:
                results.append({
                    "name": it.get("title", ""),
                    "url": it.get("link", ""),
                    "snippet": it.get("snippet", "") or "",
                })
            return results


class BingClient:
    def __init__(self, key: str | None, endpoint: str, market: str = "es-CL", timeout_s: int = 10):
        self.key = key
        self.endpoint = endpoint
        self.market = market
        self.timeout = timeout_s

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        if not self.key:
            return []
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        params = {"q": query, "mkt": self.market, "count": count, "textDecorations": False}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.endpoint, headers=headers, params=params)
            r.raise_for_status()
            j = r.json()
            web = j.get("webPages", {}).get("value", []) or []
            results = []
            for it in web:
                results.append({
                    "name": it.get("name", ""),
                    "url": it.get("url", ""),
                    "snippet": it.get("snippet", "") or "",
                })
            return results