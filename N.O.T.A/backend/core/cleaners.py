from readability import Document
from bs4 import BeautifulSoup
import trafilatura
import httpx

async def fetch_and_clean(url: str, timeout_s: int = 12) -> str:
    """Descarga y limpia HTML → texto. Intenta trafilatura y luego readability."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            html = r.text
    except Exception:
        return ""

    # Trafilatura primero
    try:
        txt = trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True)
        if txt and len(txt.strip()) > 200:
            return txt.strip()
    except Exception:
        pass

    # Readability + BeautifulSoup como fallback
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "lxml")
        text = soup.get_text("\n")
        text = "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])
        if len(text) > 200:
            return text
    except Exception:
        pass

    return ""