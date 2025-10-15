import re, math, tldextract
from collections import Counter
from typing import List, Tuple
from .types import CleanDoc

WHITELIST_WEIGHT = {
    "who.int":3, "cdc.gov":3, "nih.gov":3, "nejm.org":3, "thelancet.com":3,
    "mayoclinic.org":2, "medlineplus.gov":3, "merckmanuals.com":2, "msdmanuals.com":2,
    "gov":2, "edu":2
}

def domain_weight(url: str) -> int:
    try:
        ext = tldextract.extract(url)
        dom = f"{ext.domain}.{ext.suffix}".lower()
    except Exception:
        return 0
    w = 0
    for k,v in WHITELIST_WEIGHT.items():
        if k == ext.suffix or k in dom: w = max(w,v)
    return w

def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñ0-9]+", s.lower())

def to_vec(text: str) -> Counter:
    return Counter(tokenize(text))

def cos(a: Counter, b: Counter) -> float:
    inter = set(a) & set(b)
    num = sum(a[t]*b[t] for t in inter)
    na = math.sqrt(sum(v*v for v in a.values()) or 1)
    nb = math.sqrt(sum(v*v for v in b.values()) or 1)
    return num/(na*nb)

def split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ])", text)
    return [s.strip() for s in sents if 40 <= len(s) <= 400]

def mmr_select(candidates: List[str], q: str, k: int = 28, lam: float = .75) -> List[str]:
    qv = to_vec(q)
    cand_vecs = [to_vec(c) for c in candidates]
    selected, used = [], set()
    while len(selected) < min(k, len(candidates)):
        best_i, best_score = None, -1e9
        for i, vec in enumerate(cand_vecs):
            if i in used: continue
            rel = cos(vec, qv)
            div = max((cos(vec, to_vec(s)) for s in selected), default=0.0)
            score = lam*rel - (1-lam)*div
            if score > best_score:
                best_score, best_i = score, i
        if best_i is None: break
        used.add(best_i)
        selected.append(candidates[best_i])
    return selected

def pick_top_sentences(docs: List[CleanDoc], query: str, limit: int = 240) -> List[str]:
    q_terms = {t for t in tokenize(query) if len(t) >= 3}
    pool: List[Tuple[float, str]] = []
    for d in docs:
        w = domain_weight(d.url)
        for s in split_sentences(d.text):
            tf = sum(1 for t in q_terms if t in s.lower()) / (1+len(s))
            score = tf + 0.1*w
            if score > 0:
                pool.append((score, s))
    pool.sort(key=lambda x: -x[0])
    base = [s for _, s in pool[:limit]]
    return mmr_select(base, query, k=min(36, len(base)))