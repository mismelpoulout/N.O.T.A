import time
import numpy as np
from dataclasses import dataclass
from .embeddings import LocalEmbeddings, cosine_sim

def mmr_select(query_vec: np.ndarray, cand_vecs: np.ndarray, k=8, lam=0.7):
    chosen, pool = [], list(range(len(cand_vecs)))
    sim_q = cosine_sim(cand_vecs, query_vec[None, :]).ravel()
    while pool and len(chosen) < k:
        if not chosen:
            i = int(np.argmax(sim_q[pool]))
            chosen.append(pool.pop(i)); continue
        S = cand_vecs[chosen]
        sim_d = cosine_sim(cand_vecs[pool], S).max(axis=1)
        score = lam*sim_q[pool] - (1-lam)*sim_d
        j = int(np.argmax(score))
        chosen.append(pool.pop(j))
    return chosen

@dataclass
class Hit:
    chunk_id: int|None
    text: str
    source: str
    timestamp: float|None = None
    section: str|None = None
    negated: bool = False
    score: float = 0.0

class Ranker:
    def __init__(self, emb: LocalEmbeddings, preferred_domains: set[str]):
        self.emb = emb
        self.pref = preferred_domains

    def _domain_boost(self, url: str) -> float:
        return 1.2 if any(d in (url or "") for d in self.pref) else 1.0

    def _recency_boost(self, ts: float|None) -> float:
        if not ts: return 1.0
        years = (time.time() - ts)/(365*24*3600)
        return 1/(1 + 0.15*years)

    def rerank(self, query: str, hits: list[Hit], k: int = 10) -> list[Hit]:
        if not hits: return []
        qv = self.emb.embed([query])[0]
        cv = self.emb.embed([h.text for h in hits])
        idxs = mmr_select(qv, cv, k=min(k, len(hits)))
        picked = [hits[i] for i in idxs]
        for h in picked:
            base = 1.0
            base *= self._domain_boost(h.source)
            base *= self._recency_boost(h.timestamp)
            if h.negated: base *= 0.6
            h.score = float(base)
        picked.sort(key=lambda x: x.score, reverse=True)
        return picked