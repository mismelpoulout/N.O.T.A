from __future__ import annotations
import math, re
from collections import Counter
from typing import Iterable, Tuple
from .extract_base import tokenize, to_vec, cos
from .extract_base import domain_weight  # ya tienes esto

def usefulness_score(sentence: str, query: str, url: str, prev_vecs: Iterable[Counter]) -> float:
    # relevancia lexical
    qv = to_vec(query)
    sv = to_vec(sentence)
    rel = cos(sv, qv)
    # novedad vs lo que ya agregué
    div = 1.0
    for pv in prev_vecs:
        div = min(div, 1 - cos(sv, pv))  # más “diferente”, mayor div
    # credibilidad por dominio
    trust = 0.05 * domain_weight(url)
    # bonifica frases con cifras/tiempos (suelen ser concretas)
    concrete = 0.05 if re.search(r"\b\d", sentence) else 0.0
    return 0.65*rel + 0.25*div + trust + concrete