from typing import List, Dict
from .types import Block, CleanDoc
from .extract_base import pick_top_sentences

K_CLIN = ("diagnóstico clínico","anamnesis","examen físico","exploración","criterios clínicos")
K_LAB  = ("laboratorio","hemograma","proteína c reactiva","pcr (reactiva)","procalcitonina","serología","cultivo","antígeno","test rápido")
K_IMG  = ("rayos x","radiografía","ecografía","ultrasonido","tomografía","tc","tac","resonancia","rm")

def extract_diagnosis(docs: List[CleanDoc], query: str) -> Dict[str, Block]:
    sents = pick_top_sentences(docs, query)
    clin = [s for s in sents if any(k in s.lower() for k in K_CLIN)]
    lab  = [s for s in sents if any(k in s.lower() for k in K_LAB)]
    img  = [s for s in sents if any(k in s.lower() for k in K_IMG)]
    out: Dict[str, Block] = {}
    if clin: out["clinico"] = Block(title="Diagnóstico clínico", bullets=["• "+s for s in clin[:8]])
    if lab:  out["laboratorio"] = Block(title="Laboratorio", bullets=["• "+s for s in lab[:10]])
    if img:  out["imagen"] = Block(title="Imágenes", bullets=["• "+s for s in img[:10]])
    # diferencial si hay
    dif = [s for s in sents if "diferencial" in s.lower() or "diferenciar" in s.lower()]
    if dif: out["diferencial"] = Block(title="Diagnóstico diferencial", bullets=["• "+s for s in dif[:8]])
    return out