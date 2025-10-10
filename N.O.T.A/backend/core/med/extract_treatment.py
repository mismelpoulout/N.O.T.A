import re
from typing import List, Dict
from .types import Block, CleanDoc
from .extract_base import pick_top_sentences

DOSIS_RX = re.compile(
    r"(?P<drug>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ\- ]{3,})"
    r".{0,30}?(?P<dose>\d{1,4}\s?(?:mg|mcg|g|ml))"
    r"(?:\s*(?:cada|c\/)\s*(?P<int>\d{1,2})\s*(?:h|horas))?",
    flags=re.IGNORECASE
)

def _extract_doses(texts: List[str]) -> List[str]:
    found = []
    for t in texts:
        for m in DOSIS_RX.finditer(t):
            drug = m.group("drug").strip(" .,:;")
            dose = m.group("dose"); every = m.group("int")
            piece = f"- {drug}: {dose}" + (f" cada {every} h" if every else "")
            if piece.lower() not in (x.lower() for x in found):
                found.append(piece)
    return found[:12]

def extract_treatment(docs: List[CleanDoc], query: str) -> Dict[str, Block]:
    sents = pick_top_sentences(docs, query)
    # Clasificación simple
    conserv = [s for s in sents if any(k in s.lower() for k in ("medidas generales","reposo","hidratación","fisioterapia","rehabilitación","educación"))]
    medic   = [s for s in sents if any(k in s.lower() for k in ("tratamiento","medic","antib","analgés","antiinflam","antiviral","esteroide","inhibidor","farmac"))]
    surg    = [s for s in sents if any(k in s.lower() for k in ("quirúrg","cirug","procedimiento","técnica","laparosc","resección"))]

    out: Dict[str, Block] = {}
    if conserv: out["conservador"] = Block(title="Tratamiento conservador", bullets=["• "+s for s in conserv[:8]])
    if medic:
        doses = _extract_doses(medic)
        blk = Block(title="Tratamiento medicamentoso", bullets=["• "+s for s in medic[:10]])
        if doses: blk.extra["dosis"] = doses
        out["medicamentos"] = blk
    if surg: out["quirurgico"] = Block(title="Tratamiento quirúrgico", bullets=["• "+s for s in surg[:6]])
    return out