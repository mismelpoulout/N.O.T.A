# backend/core/rag/ingest.py
from __future__ import annotations
from typing import Iterable, Dict, Any, List
from fastembed import TextEmbedding
import numpy as np

def chunk(text: str, size: int = 700, overlap: int = 120) -> List[str]:
    words = text.split()
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i+size]))
        i += size - overlap
    return out

class Embedder:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", normalize: bool = True):
        # modelo multilingüe alternativo: "sentence-transformers/LaBSE"
        self.model = TextEmbedding(model_name=model, cache_dir=None)
        self.normalize = normalize

    def encode(self, texts: Iterable[str]) -> List[np.ndarray]:
        vecs = []
        for v in self.model.embed(texts):
            a = np.array(v, dtype=np.float32)
            if self.normalize:
                n = np.linalg.norm(a) or 1.0
                a = a / n
            vecs.append(a)
        return vecs