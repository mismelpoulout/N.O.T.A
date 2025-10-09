# backend/core/rag/compose.py
from __future__ import annotations
from typing import List, Dict

def build_context(passages: List[Dict], max_chars: int = 2000):
    acc, used_urls = [], []
    total = 0
    for p in passages:
        t = p["text"].strip()
        if total + len(t) > max_chars: break
        acc.append(t)
        total += len(t)
        if p.get("url") and p["url"] not in used_urls:
            used_urls.append(p["url"])
    return "\n\n".join(acc), used_urls

def summarize_extractivo(query: str, context: str, max_sentences: int = 7) -> str:
    # Tu función podría ser la que ya tenías (resumen por frecuencia). Minimal aquí:
    import re
    sents = re.split(r'(?<=[\.\!\?])\s+', context)
    terms = [t.lower() for t in re.findall(r'\w+', query) if len(t) > 2]
    scored = []
    for i, s in enumerate(sents):
        ls = s.lower()
        score = sum(ls.count(t) for t in terms)
        scored.append((score, i, s.strip()))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = sorted(scored[:max_sentences], key=lambda t: t[1])
    return " ".join([t[2] for t in top]).strip()