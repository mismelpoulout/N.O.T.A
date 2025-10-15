from typing import List
from .types import Block, CleanDoc
from .extract_base import pick_top_sentences

KW = ("síntoma","sintoma","signo","cuadro clínico","manifestaciones","dolor","tos","fiebre","disnea","cefalea","odinofagia","mialgia","rinorrea")

def extract_symptoms(docs: List[CleanDoc], query: str) -> Block | None:
    sents = pick_top_sentences(docs, query)
    sx = [s for s in sents if any(k in s.lower() for k in KW)]
    if not sx: return None
    return Block(title="Síntomas", bullets=["• " + s for s in sx[:12]])