# backend/core/clinical_summarizer.py
from __future__ import annotations
from typing import List, Dict
import re

GOOD_HEADS = ("definición","epidemiología","etiología","síntomas","diagnóstico","tratamiento","pronóstico","prevención","conducta")
ABSTRACT_PAT = re.compile(r"\b(randomi[sz]ed|trial|cohort|case[- ]control|hazard ratio|CI\s?\d+%|p<)\b", re.I)

def is_abstracty(s: str) -> bool:
    return bool(ABSTRACT_PAT.search(s))

def keep_clinical(sentences: List[str]) -> List[str]:
    # fuera abstracts y frases de “paper talk”
    return [s for s in sentences if not is_abstracty(s)]

def sectionize(buckets: Dict[str, List[str]], *, allow_surgery: bool) -> List[str]:
    out: List[str] = []
    # Definición + Epidemiología
    if buckets.get("definicion"):
        out += ["## Definición y Epidemiología"]
        out += _take(buckets["definicion"], 6)
    # Síntomas
    if buckets.get("sintomas"):
        out += ["", "## Síntomas"]
        out += _take(buckets["sintomas"], 10)
    # Diagnóstico
    if buckets.get("diagnostico"):
        out += ["", "## Diagnóstico", "**Métodos clínicos y complementarios:**"]
        out += _take(buckets["diagnostico"], 10)
    # Tratamiento
    if buckets.get("tratamiento"):
        out += ["", "## Tratamiento"]
        conserv = [s for s in buckets["tratamiento"] if any(x in s.lower() for x in ("rehab","educac","ejerc","no farmac","hidrat","repos"))]
        medic  = [s for s in buckets["tratamiento"] if any(x in s.lower() for x in ("metformin","insulin","antib","analg","antiinflam","farmac","antihipert"))]
        surg   = [s for s in buckets["tratamiento"] if any(x in s.lower() for x in ("cirug","oper","resecc","injerto"))]
        if conserv:
            out += ["**Tratamiento conservador:**"] + _take(conserv, 6)
        if medic:
            out += ["", "**Tratamiento medicamentoso:**"] + _take(medic, 8)
        if allow_surgery and surg:
            out += ["", "**Tratamiento quirúrgico:**"] + _take(surg, 4)
    # Conducta
    if buckets.get("conducta"):
        out += ["", "## Conducta y Seguimiento"]
        out += _take(buckets["conducta"], 8)
    return out

def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\s*\(.*?\)", "", s).strip(". ")
    return s[0].upper() + s[1:] if s else s

def _take(items: List[str], n: int) -> List[str]:
    seen, out = set(), []
    for s in items:
        s = _norm(s)
        if not s: continue
        key = re.sub(r"[^a-z0-9áéíóúüñ ]","",s.lower())
        if key in seen: continue
        seen.add(key)
        out.append("• " + (s if len(s) <= 220 else s.split(". ")[0] + "."))
        if len(out) >= n: break
    return out