import os
import httpx
from typing import List, Dict, Any, Optional

class SearchClient:
    """
    Cliente unificado para Bing o Google.
    Selecciona el motor en base a SEARCH_ENGINE (bing | google).
    """
    def __init__(self,
                 engine: Optional[str] = None,
                 bing_key: Optional[str] = None,
                 bing_endpoint: Optional[str] = None,
                 google_key: Optional[str] = None,
                 google_cx: Optional[str] = None,
                 market: str = "es-CL",
                 timeout_s: int = 10):
        self.engine = (engine or os.getenv("SEARCH_ENGINE", "bing")).lower()
        self.timeout = timeout_s

        # Configuración Bing
        self.bing_key = bing_key or os.getenv("BING_KEY")
        self.bing_endpoint = bing_endpoint or os.getenv("BING_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search")
        self.market = market

        # Configuración Google
        self.google_key = google_key or os.getenv("GOOGLE_API_KEY")
        self.google_cx = google_cx or os.getenv("GOOGLE_CX")
        self.google_endpoint = "https://www.googleapis.com/customsearch/v1"

    async def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        """
        Llama al motor de búsqueda activo.
        Si SEARCH_ENGINE=bing usa Bing API, si =google usa Google Custom Search.
        """
        if self.engine == "google":
            return await self._search_google(query, count)
        else:
            return await self._search_bing(query, count)

    # 🔵 Bing
    async def _search_bing(self, query: str, count: int) -> List[Dict[str, Any]]:
        if not self.bing_key:
            print("⚠️ No BING_KEY configurada.")
            return []
        headers = {"Ocp-Apim-Subscription-Key": self.bing_key}
        params = {"q": query, "mkt": self.market, "count": count, "textDecorations": False}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.bing_endpoint, headers=headers, params=params)
            if r.status_code != 200:
                print("❌ Bing error:", r.status_code, r.text)
                return []
            j = r.json()
            web = j.get("webPages", {}).get("value", [])
            results = []
            for it in web:
                results.append({
                    "name": it.get("name", ""),
                    "url": it.get("url", ""),
                    "snippet": it.get("snippet", "") or it.get("about", [{}])[0].get("name", "")
                })
            return results

    # 🔴 Google
    async def _search_google(self, query: str, count: int) -> List[Dict[str, Any]]:
        if not self.google_key or not self.google_cx:
            print("⚠️ No GOOGLE_API_KEY o GOOGLE_CX configurados.")
            return []
        params = {
            "key": self.google_key,
            "cx": self.google_cx,
            "q": query,
            "num": count,
            "lr": "lang_es",  # prioriza resultados en español
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.google_endpoint, params=params)
            if r.status_code != 200:
                print("❌ Google error:", r.status_code, r.text)
                return []
            j = r.json()
            results = []
            for item in j.get("items", []):
                results.append({
                    "name": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results