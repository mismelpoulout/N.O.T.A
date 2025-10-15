import re
from typing import List
from .types import Block, CleanDoc
from .extract_base import pick_top_sentences

KW = ("definición","definicion","es una","consiste en","entidad","enfermedad","etiología","epidemiología","prevalencia","incidencia","riesgo")

def extract_def_epi(docs: List[CleanDoc], query: str) -> Block | None:
    sents = pick_top_sentences(docs, query)
    chosen = [s for s in sents if any(k in s.lower() for k in KW)]
    if not chosen:
        chosen = sents[:4]
    bullets = ["• " + s for s in chosen[:8]]
    notes = []
    # Si aparece un % o tasas, lo priorizamos al inicio
    epi_hits = [b for b in bullets if re.search(r"\b\d{1,3}\s?%|\b\d+\/\d+", b)]
    bullets = epi_hits[:2] + [b for b in bullets if b not in epi_hits]
    return Block(title="Definición y epidemiología", bullets=bullets[:8], notes=notes)