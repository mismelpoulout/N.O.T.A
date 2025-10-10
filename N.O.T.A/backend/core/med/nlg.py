# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Iterable, List

# Glosario mínimo de normalización léxica (añade lo que quieras)
NORMALIZA = {
    r"\bcefal(e|é)a\b": "cefalea",
    r"\bdisnea\b": "dificultad para respirar",
    r"\bodinofagia\b": "dolor al tragar",
    r"\bSARS\-CoV\-2\b": "SARS-CoV-2",
    r"\bCOVID\s*[- ]?19\b": "COVID-19",
    r"\bP.?crp\b": "PCR (proteína C reactiva)",
    r"\bpcr\b": "PCR",
    r"\btc\b": "TAC",
    r"\brx\b": "radiografía",
}

# Sustituciones sintácticas sencillas (voz pasiva → activa, relleno → directo)
SINTAXIS = [
    (r"\bse (observa|observó|observan)\b", r"se encontró"),
    (r"\bse recomienda(n)?\b", r"se aconseja"),
    (r"\bdebería(n)? considerarse\b", r"considere"),
    (r"\bresulta(ron)?\b", r"son"),
]

# Unifica unidades y números
def _fmt_nums(s: str) -> str:
    s = re.sub(r"(\d)\s*%\b", r"\1 %", s)               # 30 %
    s = re.sub(r"\b(\d+)\s*mg\b", r"\1 mg", s)
    s = re.sub(r"\b(\d+)\s*mcg\b", r"\1 mcg", s)
    s = re.sub(r"\b(\d+)\s*ml\b", r"\1 mL", s)
    s = re.sub(r"\b(\d+)\s*h\b", r"\1 h", s)
    return s

def _compact(s: str) -> str:
    # recorta coletillas, dobles espacios y convierte a frase única clara
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*\((?:ver|como se muestra|por ejemplo).+?\)", "", s, flags=re.I)
    s = s.replace("..", ".")
    return s

def normalize_text(s: str) -> str:
    s = _fmt_nums(_compact(s))
    for pat, rep in NORMALIZA.items():
        s = re.sub(pat, rep, s, flags=re.I)
    for pat, rep in SINTAXIS:
        s = re.sub(pat, rep, s, flags=re.I)
    # primera letra minúscula si va detrás de bullet
    s = s[0].upper() + s[1:] if s and s[0].islower() else s
    return s

def rewrite_bullets(bullets: Iterable[str], max_len: int = 180) -> List[str]:
    out: List[str] = []
    seen = set()
    for b in bullets:
        t = normalize_text(re.sub(r"^[•\-\–]\s*", "", b).strip())
        # evita casi duplicados
        key = re.sub(r"[^a-z0-9áéíóúüñ ]", "", t.lower())
        if key in seen: 
            continue
        seen.add(key)
        # acorta suavemente si se pasa
        if len(t) > max_len:
            t = re.sub(r"[;,] +", ". ", t)  # parte en oraciones
            t = t.split(". ")[0].strip(". ")  # toma la primera
        out.append("• " + t)
    return out

def rewrite_doses(doses: Iterable[str]) -> List[str]:
    # Uniforma forma: "- amoxicilina: 500 mg cada 8 h"
    out = []
    for d in doses:
        dd = normalize_text(re.sub(r"^\s*[\-\•]\s*", "- ", d))
        dd = re.sub(r"\s{2,}", " ", dd)
        out.append(dd)
    return out