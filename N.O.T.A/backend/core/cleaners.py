# backend/core/cleaners.py
from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from typing import Optional

# Trafilatura opcional
try:
    import trafilatura
except Exception:
    trafilatura = None

# Readability opcional
try:
    from readability import Document  # requiere lxml + lxml_html_clean
except Exception:
    Document = None


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


async def fetch_and_clean(url: str, timeout: int = 15) -> Optional[str]:
    """
    Descarga y limpia HTML de forma resiliente.
    Orden: Trafilatura -> Readability -> BeautifulSoup (fallback).
    Devuelve texto plano o None si todo falla.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": UA},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception:
        return None

    # 1) Trafilatura (si está)
    if trafilatura is not None:
        try:
            txt = trafilatura.extract(html, include_comments=False)  # type: ignore
            if txt and len(txt.strip()) > 200:
                return txt.strip()
        except Exception:
            pass

    # 2) Readability (si está)
    if Document is not None:
        try:
            doc = Document(html)  # type: ignore
            summary_html = doc.summary()
            soup = BeautifulSoup(summary_html, "html.parser")
            txt = soup.get_text("\n", strip=True)
            if txt and len(txt.strip()) > 200:
                return txt.strip()
        except Exception:
            pass

    # 3) Fallback: BeautifulSoup directo
    try:
        soup = BeautifulSoup(html, "html.parser")
        for bad in soup(["script", "style", "noscript"]):
            bad.extract()
        txt = soup.get_text("\n", strip=True)
        if txt and len(txt.strip()) > 80:
            return txt.strip()
    except Exception:
        pass

    return None