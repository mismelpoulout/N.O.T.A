# -*- coding: utf-8 -*-
from __future__ import annotations
import math, re, sqlite3, json, time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter

# ---------------- util ----------------
_TOKEN = re.compile(r"[a-z0-9áéíóúüñ]+")

def tokenize(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())

def l2(a: List[float]) -> float:
    n = math.sqrt(sum(x * x for x in a))
    return n if n > 0 else 1.0

def _zscore(xs: List[float], x: float) -> float:
    if not xs:
        return 0.0
    mu = sum(xs) / len(xs)
    var = sum((v - mu) ** 2 for v in xs) / max(1, len(xs) - 1)
    sd = math.sqrt(var) or 1.0
    return (x - mu) / sd

# ---------------- Dense embeddings (degradado) ----------------
class DenseBackend:
    """
    Intenta fastembed -> sentence-transformers -> hashing (BoW) como último recurso.
    Todas devuelven vectores List[float] normalizados L2.
    """
    def __init__(self, model: str | None = None):
        self.kind = "hashing"
        self.dim = 256
        self.model = None

        # 1) fastembed
        try:
            from fastembed import TextEmbedding  # type: ignore
            self.model = TextEmbedding(model_name=(model or "BAAI/bge-small-en-v1.5"))
            # cuidado: .embed devuelve generador
            v = next(self.model.embed(["ok"]))
            self.dim = len(v)
            self.kind = "fastembed"
        except Exception:
            self.model = None

        # 2) sentence-transformers
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self.model = SentenceTransformer(model or "sentence-transformers/all-MiniLM-L6-v2")
                self.dim = int(self.model.get_sentence_embedding_dimension())
                self.kind = "sbert"
            except Exception:
                self.model = None
                self.kind = "hashing"
                self.dim = 256

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self.kind == "fastembed":
            vecs = []
            for v in self.model.embed(texts):  # generator
                # ya viene normalizado; por si acaso normalizamos
                v = list(v)
                n = l2(v)
                vecs.append([x / n for x in v])
            return vecs

        if self.kind == "sbert":
            import numpy as np  # type: ignore
            arr = self.model.encode(texts, normalize_embeddings=True)
            return [list(map(float, v)) for v in arr]

        # hashing fallback (BoW -> vector fijo)
        vecs: List[List[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in tokenize(t):
                v[hash(tok) % self.dim] += 1.0
            n = l2(v)
            vecs.append([x / n for x in v])
        return vecs

# ---------------- BM25 backend (degradado) ----------------
class BM25Backend:
    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self._ensure_tables()
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            self._has_rankbm25 = True
            self.BM25Okapi = BM25Okapi
        except Exception:
            self._has_rankbm25 = False

        self._reload_corpus()

    def _ensure_tables(self) -> None:
        self.con.execute("""
        CREATE TABLE IF NOT EXISTS bm25_index(
          chunk_id TEXT PRIMARY KEY,
          tokens   TEXT
        )""")
        self.con.commit()

    def _reload_corpus(self) -> None:
        self._corpus: Dict[str, List[str]] = {}
        cur = self.con.execute("SELECT chunk_id, tokens FROM bm25_index")
        for cid, toks in cur.fetchall():
            self._corpus[cid] = (toks or "").split()

        if self._has_rankbm25:
            self._ids = list(self._corpus.keys())
            self._bm = self.BM25Okapi(list(self._corpus.values()))
        else:
            # precompute idf para versión simplificada
            N = max(1, len(self._corpus))
            df: Counter = Counter()
            for toks in self._corpus.values():
                for t in set(toks):
                    df[t] += 1
            self._idf = {t: math.log((N - df[t] + 0.5) / (df[t] + 0.5) + 1.0) for t in df}

    def search(self, query: str, top_k: int = 50) -> List[Tuple[str, float]]:
        if not self._corpus:
            return []
        q_toks = tokenize(query)
        if self._has_rankbm25:
            scores = self._bm.get_scores(q_toks)
            pairs = list(zip(self._ids, map(float, scores)))
            pairs.sort(key=lambda x: x[1], reverse=True)
            return pairs[:top_k]

        # simple BM25-ish
        k1, b = 1.5, 0.75
        avgdl = sum(len(v) for v in self._corpus.values()) / max(1, len(self._corpus))
        out: List[Tuple[str, float]] = []
        for cid, toks in self._corpus.items():
            dl = len(toks) or 1
            tf = Counter(toks)
            score = 0.0
            for t in q_toks:
                if t not in tf or t not in self._idf:
                    continue
                num = tf[t] * (k1 + 1)
                den = tf[t] + k1 * (1 - b + b * dl / avgdl)
                score += self._idf[t] * (num / den)
            out.append((cid, float(score)))
        out.sort(key=lambda x: x[1], reverse=True)
        return out[:top_k]

# ---------------- Hybrid retriever ----------------
@dataclass
class Chunk:
    id: str
    url: str
    title: str
    section: str
    text: str
    published_at: float | None
    evidence_score: float

class HybridRetriever:
    """
    Fusiona búsqueda densa y lexical, devuelve chunks con metadatos.
    Requiere SQLite con tablas:
      - doc_chunks(id TEXT PK, url, title, section, chunk, published_at REAL, evidence_score REAL)
      - vec_index(chunk_id TEXT PK, embedding_json TEXT)        [opcional]
      - bm25_index(chunk_id TEXT PK, tokens TEXT)               [opcional]
    """
    def __init__(self, db_path: str, dense_model: str | None = None):
        self.db_path = db_path
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = sqlite3.Row
        self._ensure_doc_tables()

        self.dense = DenseBackend(dense_model)
        self.bm25 = BM25Backend(self.con)
        self._embs: Dict[str, List[float]] = self._load_embeddings()

    def _ensure_doc_tables(self) -> None:
        # doc_chunks (si ingest aún no lo creó)
        self.con.execute("""
        CREATE TABLE IF NOT EXISTS doc_chunks(
          id TEXT PRIMARY KEY,
          url TEXT,
          title TEXT,
          section TEXT,
          chunk TEXT,
          published_at REAL,
          evidence_score REAL
        )""")
        self.con.commit()

    def _load_embeddings(self) -> Dict[str, List[float]]:
        embs: Dict[str, List[float]] = {}
        try:
            self.con.execute("""CREATE TABLE IF NOT EXISTS vec_index(
                chunk_id TEXT PRIMARY KEY,
                embedding_json TEXT
            )""")
            for cid, ej in self.con.execute("SELECT chunk_id, embedding_json FROM vec_index"):
                try:
                    embs[cid] = json.loads(ej)
                except Exception:
                    pass
        except Exception:
            # tabla realmente no disponible: OK
            pass
        return embs

    # --------- util: coseno ----------
    @staticmethod
    def _cos(a: List[float], b: List[float]) -> float:
        num = sum(x * y for x, y in zip(a, b))
        return num / (l2(a) * l2(b))

    def _load_chunk(self, cid: str) -> Optional[Chunk]:
        c = self.con.execute(
            "SELECT id,url,title,section,chunk,published_at,evidence_score FROM doc_chunks WHERE id=?",
            (cid,)
        ).fetchone()
        if not c:
            return None
        return Chunk(
            id=c["id"],
            url=c["url"] or "",
            title=c["title"] or "",
            section=c["section"] or "otros",
            text=c["chunk"] or "",
            published_at=c["published_at"],
            evidence_score=float(c["evidence_score"] or 0.0),
        )

    def search(self, query: str, *, top_k_dense: int = 50, top_k_lex: int = 50, top_k: int = 40) -> List[Dict]:
        # --- denso
        dense_top: List[Tuple[str, float]] = []
        if self._embs:
            qv = self.dense.embed([query])[0]
            dense_scores = [(cid, self._cos(qv, emb)) for cid, emb in self._embs.items()]
            dense_scores.sort(key=lambda x: x[1], reverse=True)
            dense_top = dense_scores[:top_k_dense]

        # --- léxico
        lex_top = self.bm25.search(query, top_k=top_k_lex)

        # --- fusión de características
        pool: Dict[str, Dict[str, float]] = defaultdict(lambda: {"cos": 0.0, "bm25": 0.0})
        for cid, s in dense_top:
            pool[cid]["cos"] = float(s)
        for cid, s in lex_top:
            pool[cid]["bm25"] = float(s)

        # normalizaciones para score final
        cos_vals = [v["cos"] for v in pool.values()]
        bm_vals  = [v["bm25"] for v in pool.values()]

        results: List[Dict] = []
        now = time.time()
        for cid, feats in pool.items():
            ch = self._load_chunk(cid)
            if not ch:
                continue

            cos_z = _zscore(cos_vals, feats["cos"]) if cos_vals else 0.0
            bm_z  = _zscore(bm_vals,  feats["bm25"]) if bm_vals  else 0.0

            # recencia (0..1) con semivida ~3 años
            rec = 0.0
            if ch.published_at:
                age_days = max(0.0, (now - float(ch.published_at)) / 86400.0)
                rec = math.exp(-age_days / (365.0 * 3.0))

            # score final con pesos moderados
            score = 0.55 * cos_z + 0.35 * bm_z + 0.15 * ch.evidence_score + 0.05 * rec

            results.append({
                "chunk_id": ch.id,
                "url": ch.url,
                "title": ch.title,
                "section": ch.section,
                "chunk": ch.text,
                "published_at": ch.published_at or 0.0,
                "evidence_score": ch.evidence_score,
                "cos": feats["cos"],
                "bm25": feats["bm25"],
                "score": float(score),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ---------------- indexado (para ingest) ----------------
    def upsert_embedding(self, chunk_id: str, text: str) -> None:
        v = self.dense.embed([text])[0]
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS vec_index(
              chunk_id TEXT PRIMARY KEY,
              embedding_json TEXT
            )""")
        self.con.execute(
            "REPLACE INTO vec_index(chunk_id, embedding_json) VALUES(?,?)",
            (chunk_id, json.dumps(v))
        )
        self.con.commit()
        # refrescar cache en memoria
        self._embs[chunk_id] = v

    def upsert_bm25_tokens(self, chunk_id: str, text: str) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS bm25_index(
              chunk_id TEXT PRIMARY KEY,
              tokens TEXT
            )""")
        toks = " ".join(tokenize(text))
        self.con.execute("REPLACE INTO bm25_index(chunk_id, tokens) VALUES(?,?)", (chunk_id, toks))
        self.con.commit()
        # recargar corpus para búsquedas inmediatas
        self.bm25._reload_corpus()