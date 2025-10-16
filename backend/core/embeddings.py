import numpy as np
from fastembed import TextEmbedding

class LocalEmbeddings:
    """
    fastembed CPU-only. Modelo por defecto: 'sentence-transformers/all-MiniLM-L6-v2'
    (fastembed lo descarga y cachea). Dim ~384.
    """
    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model
        self.encoder = TextEmbedding(model_name=model)

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = list(self.encoder.embed(texts))
        return np.asarray(vecs, dtype=np.float32)

def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return a @ b.T