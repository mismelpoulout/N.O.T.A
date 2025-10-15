import httpx
from typing import List, Dict, Any

class BingClient:
    def __init__(self, key: str | None, endpoint: str | None, market: str = "es-CL", timeout_s: int = 10):
        self.key = key
        self.endpoint = endpoint or "https://api.bing.microsoft.com/v7.0/search"
        self.market = market
        self.timeout = timeout_s

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        """Búsqueda general en la web. Si no hay key, retorna []."""
        if not self.key:
            return []
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        params = {"q": query, "mkt": self.market, "count": count, "textDecorations": False}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.endpoint, headers=headers, params=params)
            r.raise_for_status()
            j = r.json()
            web = j.get("webPages", {}).get("value", [])
            # normaliza
            results = []
            for it in web:
                results.append({
                    "name": it.get("name", ""),
                    "url": it.get("url", ""),
                    "snippet": it.get("snippet", "") or it.get("about", [{}])[0].get("name", "")
                })
            return results