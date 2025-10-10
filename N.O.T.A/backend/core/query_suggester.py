# -*- coding: utf-8 -*-
"""
Genera 3 sugerencias de preguntas relacionadas con la consulta actual.
Devuelve estructuras JSON para mostrar con hover/click interactivo.
"""
from __future__ import annotations
import random
from typing import List, Dict

def generate_related_queries(query: str, context: str) -> List[Dict]:
    ql = query.lower()
    suggestions: List[str] = []

    if "qué es" in ql or "definición" in ql:
        suggestions = [
            f"Principales complicaciones de {query}",
            f"Cómo se diagnostica {query}",
            f"Tratamientos actuales para {query}"
        ]
    elif any(k in ql for k in ("tratamiento", "manejo")):
        suggestions = [
            f"Efectos secundarios de los tratamientos para {query}",
            f"Nuevas terapias experimentales para {query}",
            f"Guías clínicas recientes sobre {query}"
        ]
    elif "síntoma" in ql:
        suggestions = [
            f"Diagnóstico diferencial de {query}",
            f"Cuándo acudir al médico por {query}",
            f"Pruebas recomendadas ante {query}"
        ]
    else:
        suggestions = [
            f"Pronóstico y evolución de {query}",
            f"Diferencias entre {query} y condiciones similares",
            f"Prevención y medidas profilácticas para {query}"
        ]

    random.shuffle(suggestions)
    return [
        {"title": s.capitalize(), "query": s, "hoverText": "Explorar este tema"}
        for s in suggestions[:3]
    ]