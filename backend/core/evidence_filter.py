# backend/core/evidence_filter.py
from __future__ import annotations
from typing import List, Dict
import re

GUIDE_DOMAINS = ("minsal.cl","msdmanuals.com","merckmanuals.com","nih.gov","niddk.nih.gov","who.int","cdc.gov","mayoclinic.org","medlineplus.gov","paho.org")
PAPER_HINT = re.compile(r"\b(randomi[sz]ed|meta[- ]analysis|systematic review|trial|cohort|odds ratio|hazard ratio)\b", re.I)

def doc_quality(url: str, title: str) -> int:
    u = (url or "").lower()
    score = 0
    for d in GUIDE_DOMAINS:
        if d in u: score += 3
    if "guideline" in u or "guia" in u or "consenso" in u: score += 3
    if PAPER_HINT.search(title or ""): score -= 1
    if "wikipedia.org" in u: score -= 1
    return score

def drop_paperish(sentences: List[str]) -> List[str]:
    return [s for s in sentences if not PAPER_HINT.search(s)]