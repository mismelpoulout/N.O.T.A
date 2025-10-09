# backend/core/search_client.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import httpx

class GoogleCSEClient:
    def __init__(self, api_key: str, cx: str, timeout_s: int = 10):
        self.api_key, self.cx = api_key, cx
        self.endpoint = "https://www.googleapis.com/customsearch/v1"
        self.timeout = timeout_s

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        if not self.api_key or not self.cx:
            return []
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(count, 10),
            "safe": "active",
            "hl": "es",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.endpoint, params=params)
            r.raise_for_status()
            j = r.json()
            items = j.get("items", []) or []
            return [{
                "name": it.get("title", ""),
                "url": it.get("link", ""),
                "snippet": it.get("snippet", ""),
            } for it in items]


class BingClient:
    def __init__(self, key: str, endpoint: Optional[str] = None, market: str = "es-CL", timeout_s: int = 10):
        self.key = key
        self.endpoint = endpoint or "https://api.bing.microsoft.com/v7.0/search"
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
            return [{
                "name": it.get("name", ""),
                "url": it.get("url", ""),
                "snippet": it.get("snippet", "") or "",
            } for it in web]


class SearchClient:
    """
    Envoltura con .search() y selector por entorno.
    """
    def __init__(self, impl):
        self.impl = impl

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        if not self.impl:
            return []
        return await self.impl.search(query, count=count)

    @classmethod
    def from_env(cls, cfg: dict) -> "SearchClient":
        engine = (cfg.get("SEARCH_ENGINE") or "").strip().lower()
        if engine == "google":
            key = cfg.get("GOOGLE_API_KEY") or cfg.get("GOOGLE_KEY")
            cx = cfg.get("GOOGLE_CX")
            impl = GoogleCSEClient(api_key=key, cx=cx) if key and cx else None
            return cls(impl)
        if engine == "bing":
            key = cfg.get("BING_KEY")
            ep  = cfg.get("BING_ENDPOINT")
            mkt = cfg.get("BING_MKT", "es-CL")
            impl = BingClient(key=key, endpoint=ep, market=mkt) if key else None
            return cls(impl)
        # sin motor configurado
        return cls(None)