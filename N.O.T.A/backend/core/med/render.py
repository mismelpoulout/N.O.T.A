from __future__ import annotations
from typing import List, Iterable
from .types import ExtractionResult, Block
from .nlg import rewrite_bullets, rewrite_doses

def _render_block(b: Block) -> str:
    bullets = rewrite_bullets(b.bullets)
    out = [f"## {b.title}", *bullets]
    if b.notes:
        out += rewrite_bullets(b.notes)
    if "dosis" in b.extra and b.extra["dosis"]:
        out.append("\n**Dosis (confirmar con guía local):**")
        out += rewrite_doses(b.extra["dosis"])
    return "\n".join(out)

def render_markdown(query: str, R: ExtractionResult) -> str:
    sec: List[str] = [f"**Pregunta:** {query}\n"]

    if R.definicion: sec.append(_render_block(R.definicion))
    if R.sintomas:   sec.append(_render_block(R.sintomas))

    if R.diagnostico:
        for key in ("clinico","laboratorio","imagen","diferencial"):
            blk = R.diagnostico.get(key)
            if blk: sec.append(_render_block(blk))

    if R.tratamiento:
        for key in ("conservador","medicamentos","quirurgico"):
            blk = R.tratamiento.get(key)
            if blk: sec.append(_render_block(blk))

    if R.conducta: sec.append(_render_block(R.conducta))

    sec.append("## Otras sugerencias")
    sec += [
        "- Pronóstico y complicaciones relacionadas",
        "- Diferenciales clave que no debe pasar por alto",
        "- Prevención y educación del paciente",
    ]

    if R.citations:
        sec.append("## Referencias principales")
        sec.append("\n".join(f"{i+1}. {u}" for i,u in enumerate(R.citations, 1)))
    else:
        sec.append("## Referencias principales\n– (sin referencias)")

    return "\n\n".join(sec).strip()