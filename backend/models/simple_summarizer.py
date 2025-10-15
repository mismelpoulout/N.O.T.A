from typing import List
import re

def _sentences(text: str) -> List[str]:
    # separador simple por punto, signo de exclamación o interrogación
    return [s.strip() for s in re.split(r'(?<=[\.\!\?])\s+', text) if s.strip()]

def summarize_bullets(q: str, passages: List[str], max_bullets: int = 6) -> str:
    """
    Resumen local extractivo y rápido:
    - Se arma una bolsa de palabras para ponderar oraciones.
    - Se seleccionan las mejores oraciones como viñetas.
    """
    bag = {}
    for p in passages:
        for w in re.findall(r'\b[\wáéíóúñç]+\b', p.lower()):
            if len(w) > 3:
                bag[w] = bag.get(w, 0) + 1

    scored = []
    for p in passages:
        for s in _sentences(p)[:10]:  # primeras oraciones de cada pasaje
            score = sum(bag.get(w, 0) for w in re.findall(r'\b[\wáéíóúñç]+\b', s.lower()))
            scored.append((score, s))

    bullets = [f"• {s}" for _, s in sorted(scored, reverse=True)[:max_bullets]]
    if bullets:
        return "\n".join(bullets)
    # fallback
    return (passages[0] if passages else "").strip()[:400]
