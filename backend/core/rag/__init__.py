# backend/core/rag/__init__.py
# Reexporta solo los componentes RAG
from .store import VectorStore          # noqa: F401
from .ingest import Embedder, chunk     # noqa: F401
from .retrieve import Retriever         # noqa: F401
from .compose import build_context, summarize_extractivo  # noqa: F401