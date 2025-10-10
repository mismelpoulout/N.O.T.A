# -*- coding: utf-8 -*-
from __future__ import annotations
import re, tldextract

# Heurística: guideline > revisión > ECA > observacional > sitio divulgación > blog
EVIDENCE_WEIGHTS = {
    "guideline": 4.0, "consensus": 3.5, "recomendación": 3.2, "guía": 3.2,
    "systematic review": 3.0, "revisión sistemática": 3.0, "meta-analysis": 3.0, "metaanálisis": 3.0,
    "randomized": 2.6, "ensayo aleatorizado": 2.6,
    "cohort": 2.2, "case-control": 2.0, "observational": 1.8,
    "review": 1.4,
    "case report": 1.0, "serie de casos": 1.0,
    "blog": 0.3, "opinión": 0.4
}

# dominio: prioriza .gov/.edu + sitios médicos fuertes
DOMAIN_BOOST = {
    "gov": 1.0, "edu": 0.8,
    "who.int": 1.2, "cdc.gov": 1.2, "nih.gov": 1.1, "nejm.org": 1.0,
    "thelancet.com": 1.0, "bmj.com": 0.9, "mayoclinic.org": 0.8,
    "merckmanuals.com": 0.7, "msdmanuals.com": 0.7,
}

def evidence_score(text: str, url: str = "", title: str = "") -> float:
    blob = f"{title} {text}".lower()
    sc = 0.0
    for k, w in EVIDENCE_WEIGHTS.items():
        if re.search(rf"\b{k}\b", blob):
            sc = max(sc, w)

    # señal por dominio
    try:
        ext = tldextract.extract(url)
        dom = f"{ext.domain}.{ext.suffix}".lower()
        suf = ext.suffix.lower()
    except Exception:
        dom, suf = "", ""
    for k, b in DOMAIN_BOOST.items():
        if k == suf or k in dom:
            sc += b

    # clamp
    return max(0.0, min(sc, 6.0))