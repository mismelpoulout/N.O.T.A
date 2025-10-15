# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Ingesta de fuentes a RAG (documents, doc_chunks, bm25_index, vec_index).

Ejemplos:
  python -m backend.core.rag.ingest --db backend/data/rag.db --file data/guia.txt --url https://... --title "Guía X"
  python -m backend.core.rag.ingest --db backend/data/rag.db --dir ./corpus_txt
"""

import argparse
import json
import math
import os
import re
import sqlite3
import time
import uuid
from typing import Iterable, List, Tuple

# deps internas
from backend.core.evidence import evidence_score

# ------------------------- util de tokenización -------------------------
_tok = re.compile(r"[a-z0-9áéíóúüñ]+")

def tokenize(text: str) -> List[str]:
    return _tok.findall((text or "").lower())

# ------------------------- Embedder robusto (con fallback) -------------------------
class Embedder:
    """
    Intenta usar fastembed. Si no está disponible, cae a sentence-transformers
    y finalmente a un hashing-vector (determinista).
    """
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", normalize: bool = True):
        self.normalize = normalize
        self.kind = "hashing"
        self.dim = 384  # tamaño por defecto para fallback hashing

        self._fe = None
        self._sbert = None

        # fastembed
        try:
            from fastembed import TextEmbedding  # type: ignore
            self._fe = TextEmbedding(model_name=model, cache_dir=None)
            # obtener dim con un embedding de prueba
            v = list(self._fe.embed(["ok"]))[0]
            self.dim = len(v)
            self.kind = "fastembed"
        except Exception:
            # sentence-transformers
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self._sbert = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                self.dim = self._sbert.get_sentence_embedding_dimension()
                self.kind = "sbert"
            except Exception:
                self._fe = None
                self._sbert = None
                self.kind = "hashing"

    def _norm(self, arr: List[float]) -> List[float]:
        if not self.normalize:
            return arr
        n = math.sqrt(sum(x*x for x in arr)) or 1.0
        return [x / n for x in arr]

    def encode(self, texts: Iterable[str]) -> List[List[float]]:
        if self.kind == "fastembed" and self._fe:
            out = []
            for v in self._fe.embed(texts):  # generator
                out.append(self._norm(list(v)))
            return out
        if self.kind == "sbert" and self._sbert:
            import numpy as np  # type: ignore
            arr = self._sbert.encode(list(texts), normalize_embeddings=self.normalize)
            return [list(map(float, v)) for v in (arr if isinstance(arr, list) else arr.tolist())]
        # hashing fallback
        vecs: List[List[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in tokenize(t):
                v[hash(tok) % self.dim] += 1.0
            vecs.append(self._norm(v))
        return vecs

# ------------------------- Chunking -------------------------
def chunk_words(text: str, size: int = 700, overlap: int = 120) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        i += max(1, size - overlap)
    return out

def chunk_sentences(text: str, max_chars: int = 900) -> List[str]:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ])", text)
    out: List[str] = []
    cur = ""
    for s in sents:
        if len(cur) + len(s) + 1 <= max_chars:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                out.append(cur)
            cur = s
    if cur:
        out.append(cur)
    return out

# ------------------------- Secciones clínicas -------------------------
HEADERS = (
    "definición", "definicion",
    "síntomas", "sintomas", "signos",
    "diagnóstico", "diagnostico",
    "tratamiento", "manejo", "terapia",
    "conducta", "seguimiento"
)

def detect_section_key(header_line_lower: str) -> str:
    if "defin" in header_line_lower:
        return "definicion"
    if "sintom" in header_line_lower or "sign" in header_line_lower:
        return "sintomas"
    if "diagn" in header_line_lower:
        return "diagnostico"
    if "trat" in header_line_lower or "manejo" in header_line_lower or "terap" in header_line_lower:
        return "tratamiento"
    if "conduct" in header_line_lower or "seguim" in header_line_lower:
        return "conducta"
    return "otros"

def split_sections(text: str) -> List[Tuple[str, str]]:
    """
    Corta por encabezados de sección; si no se detectan, devuelve todo como 'otros'.
    """
    lines = re.split(r"\n+", text or "")
    out: List[Tuple[str, str]] = []
    cur_key = "otros"
    cur_buf: List[str] = []

    def flush():
        if cur_buf:
            out.append((cur_key, "\n".join(cur_buf).strip()))

    for ln in lines:
        l = ln.strip()
        if not l:
            continue
        low = l.lower()
        if any(low.startswith(h) for h in HEADERS) or re.match(r"^#{1,3}\s+", l):
            flush()
            cur_key = detect_section_key(low)
            cur_buf = [l]
        else:
            cur_buf.append(l)
    flush()
    return out or [("otros", text or "")]

# ------------------------- SQLite helpers -------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  url TEXT,
  title TEXT,
  published_at REAL,
  evidence_score REAL
);
CREATE TABLE IF NOT EXISTS doc_chunks(
  id TEXT PRIMARY KEY,
  doc_id TEXT,
  url TEXT,
  title TEXT,
  section TEXT,
  chunk TEXT,
  published_at REAL,
  evidence_score REAL,
  FOREIGN KEY(doc_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS bm25_index(
  chunk_id TEXT PRIMARY KEY,
  tokens TEXT
);
CREATE TABLE IF NOT EXISTS vec_index(
  chunk_id TEXT PRIMARY KEY,
  embedding_json TEXT
);
"""

def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    con.commit()

# ------------------------- Ingesta -------------------------
def upsert_document(con: sqlite3.Connection, url: str, title: str, published_at: float, ev: float) -> str:
    doc_id = str(uuid.uuid4())
    con.execute(
        "INSERT INTO documents(id,url,title,published_at,evidence_score) VALUES(?,?,?,?,?)",
        (doc_id, url, title, published_at, ev),
    )
    return doc_id

def insert_chunk_and_indexes(
    con: sqlite3.Connection,
    emb: Embedder,
    doc_id: str,
    url: str,
    title: str,
    section: str,
    chunk_text: str,
    published_at: float,
    ev: float,
) -> None:
    chunk_id = str(uuid.uuid4())
    con.execute(
        """INSERT INTO doc_chunks(id,doc_id,url,title,section,chunk,published_at,evidence_score)
           VALUES(?,?,?,?,?,?,?,?)""",
        (chunk_id, doc_id, url, title, section, chunk_text, published_at, ev),
    )
    # bm25
    toks = " ".join(tokenize(chunk_text))
    con.execute("REPLACE INTO bm25_index(chunk_id, tokens) VALUES(?,?)", (chunk_id, toks))
    # dense
    vec = emb.encode([chunk_text])[0]
    con.execute("REPLACE INTO vec_index(chunk_id, embedding_json) VALUES(?,?)", (chunk_id, json.dumps(vec)))
    con.commit()

def ingest_text_file(con: sqlite3.Connection, emb: Embedder, path: str, url: str = "", title: str = "") -> None:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    ev = evidence_score(raw[:2000], url, title)
    published_at = time.time()  # si no se conoce, timestamp actual
    doc_id = upsert_document(con, url, title or os.path.basename(path), published_at, ev)

    # partir por secciones
    for sec_key, block in split_sections(raw):
        # primer intento: chunk por oraciones
        chunks = chunk_sentences(block, max_chars=900)
        # respaldo: forzar por palabras con solapamiento
        if not chunks:
            chunks = chunk_words(block, size=700, overlap=120)
        for ch in chunks:
            if not ch.strip():
                continue
            insert_chunk_and_indexes(con, emb, doc_id, url, title, sec_key, ch, published_at, ev)

    print(f"[ingest] {os.path.basename(path)} -> {doc_id}  ({len(list(split_sections(raw)))} secciones)")

# ------------------------- CLI -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Ruta a la DB RAG (e.g., backend/data/rag.db)")
    ap.add_argument("--file", help="Ruta a un archivo .txt/.md a ingerir")
    ap.add_argument("--url", default="", help="URL original (opcional)")
    ap.add_argument("--title", default="", help="Título del documento (opcional)")
    ap.add_argument("--dir", help="Carpeta con múltiples .txt/.md")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5", help="Modelo para embeddings densos")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    con = sqlite3.connect(args.db)
    ensure_schema(con)

    emb = Embedder(model=args.model, normalize=True)

    if args.file:
        ingest_text_file(con, emb, args.file, url=args.url or "", title=args.title or "")

    if args.dir:
        for name in os.listdir(args.dir):
            p = os.path.join(args.dir, name)
            if os.path.isfile(p) and any(p.lower().endswith(ext) for ext in (".txt", ".md", ".markdown")):
                ingest_text_file(con, emb, p, url="", title=os.path.splitext(name)[0])

    con.close()

if __name__ == "__main__":
    main()