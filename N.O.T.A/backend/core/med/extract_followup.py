from typing import List
from .types import Block, CleanDoc
from .extract_base import pick_top_sentences

KW = ("seguimiento","conducta","derivar","derivación","criterios de ingreso","urgente","control","alerta","banderas rojas","alta","manejo ambulatorio")

def extract_followup(docs: List[CleanDoc], query: str) -> Block | None:
    sents = pick_top_sentences(docs, query)
    cx = [s for s in sents if any(k in s.lower() for k in KW)]
    if not cx: return None
    return Block(title="Conducta y seguimiento", bullets=["• "+s for s in cx[:10]])