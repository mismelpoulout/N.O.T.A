from dataclasses import dataclass
import numpy as np
from .embeddings import LocalEmbeddings, cosine_sim

@dataclass(frozen=True)
class Section:
    name: str
    prototypes: list[str]

CLIN_SECTIONS: list[Section] = [
    Section("motivo_consulta", ["motivo de consulta", "consulta por", "viene por"]),
    Section("antecedentes",     ["antecedentes personales", "historial médico", "comorbilidades"]),
    Section("sintomas",         ["síntomas", "refiere", "presenta", "dolor", "fiebre", "tos"]),
    Section("examen_fisico",    ["examen físico", "signos vitales", "exploración"]),
    Section("diagnostico",      ["diagnóstico", "impresión diagnóstica"]),
    Section("plan",             ["plan", "conducta", "tratamiento", "indicación"]),
]

class ClinSectionClassifier:
    def __init__(self, embed: LocalEmbeddings):
        self.embed = embed
        self.proto_texts   = [p for s in CLIN_SECTIONS for p in s.prototypes]
        self.proto_labels  = [s.name for s in CLIN_SECTIONS for _ in s.prototypes]
        self.proto_vecs    = self.embed.embed(self.proto_texts)

    def predict(self, sentences: list[str]) -> list[str]:
        if not sentences:
            return []
        X = self.embed.embed(sentences)
        S = cosine_sim(X, self.proto_vecs)
        idx = S.argmax(axis=1)
        return [self.proto_labels[i] for i in idx]