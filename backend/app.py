# backend/app.py
import os
import time
import inspect
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import dotenv_values

# -----------------------------------------------------------------------------
# Config (.env + entorno)
# -----------------------------------------------------------------------------
cfg = {**dotenv_values("backend/.env"), **os.environ}

DATA_DIR = cfg.get("DATA_DIR", "./backend/data")
SQLITE_DB = cfg.get("SQLITE_DB", f"{DATA_DIR.rstrip('/')}/medical.db")  # pipeline RAG local
ALLOWED = cfg.get("ALLOWED_ORIGINS", "*")
TRUSTED_HOSTS = [h.strip() for h in (cfg.get("TRUSTED_HOSTS") or "").split(",") if h.strip()]
FORCE_HTTPS = (cfg.get("FORCE_HTTPS", "false").lower() in ("1", "true", "yes"))
ENV = (cfg.get("ENV") or "production").lower()          # "development" | "production"
SERVER_API_KEY = cfg.get("SERVER_API_KEY")              # opcional, para proteger /chat

# Compat con pipeline anterior (si lo sigues usando)
IOS_FTS_DB = cfg.get("IOS_FTS_DB", f"{DATA_DIR.rstrip('/')}/medical_fts.sqlite")
OUTPUT_DB = cfg.get("OUTPUT_DB", f"{DATA_DIR.rstrip('/')}/output.db")

PREFERRED_DOMAINS = [
    d.strip()
    for d in (cfg.get("PREFERRED_DOMAINS", "").split(",") if cfg.get("PREFERRED_DOMAINS") else [])
    if d.strip()
]

# -----------------------------------------------------------------------------
# FastAPI (oculta docs en prod por defecto)
# -----------------------------------------------------------------------------
show_docs = ENV == "development" or (cfg.get("ENABLE_DOCS", "false").lower() in ("1", "true", "yes"))
app = FastAPI(
    title="N.O.T.A",
    version="0.6.2",
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None,
)

# -----------------------------------------------------------------------------
# Middlewares
# -----------------------------------------------------------------------------
allow_origins = ["*"] if ALLOWED == "*" else [o.strip() for o in ALLOWED.split(",") if o.strip()]
# Si permites "*", también permite todos los headers para evitar CORS raros
allow_headers = ["*"] if allow_origins == ["*"] else ["Authorization", "X-API-Key", "Content-Type"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=allow_headers,
)
app.add_middleware(GZipMiddleware, minimum_size=800)

if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

if FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)

# -----------------------------------------------------------------------------
# Pipeline (auto-detección robusta con introspección)
# -----------------------------------------------------------------------------
def build_pipeline():
    """
    Detecta la firma real de backend.core.pipeline.NOTAPipeline y construye
    con kwargs correctos. Casos soportados:
      A) __init__(db_path | sqlite_path | db)
      B) __init__(db_dir, search_client, ios_fts_db, output_db, preferred_domains)
      C) __init__(db_dir | data_dir)
      D) __init__(search_client=...)
    """
    from backend.core.pipeline import NOTAPipeline as AnyPipeline
    sig = inspect.signature(AnyPipeline.__init__)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    names = [p.name for p in params]

    print(f"🧠 NOTAPipeline importado de: {AnyPipeline.__module__}")
    print(f"🧠 Firma __init__: {sig}")

    # Caso A: RAG local (embeddings + SQLite)
    if len(params) == 1 and names[0] in ("db_path", "sqlite_path", "db"):
        kw = {names[0]: SQLITE_DB}
        return AnyPipeline(**kw), "RAG-local"

    # Prepara search_client (para legacy)
    search_client = None
    try:
        from backend.core.search_client import SearchClient
        search_client = SearchClient.from_env(cfg)
    except Exception as e:
        print(f"⚠️ No se pudo inicializar SearchClient: {e}")

    # Caso B: Legacy completo con kwargs
    need = {"db_dir", "search_client", "ios_fts_db", "output_db", "preferred_domains"}
    if set(names) >= need:
        return AnyPipeline(
            db_dir=DATA_DIR,
            search_client=search_client,
            ios_fts_db=IOS_FTS_DB,
            output_db=OUTPUT_DB,
            preferred_domains=PREFERRED_DOMAINS,
        ), "legacy-search-kwargs"

    # Caso C: Legacy mínimo con data
    if len(params) == 1 and names[0] in ("db_dir", "data_dir"):
        return AnyPipeline(**{names[0]: DATA_DIR}), "legacy-min-data"

    # Caso D: Legacy mínimo con search_client
    if len(params) == 1 and names[0] == "search_client":
        return AnyPipeline(search_client=search_client), "legacy-min-search-client"

    # Si nada coincide, avisar claramente
    raise RuntimeError(
        f"NOTAPipeline.__init__() no coincide con firmas esperadas. Recibida: {sig}. "
        f"Actualiza backend/core/pipeline.py o ajusta este constructor."
    )

pipe, pipeline_mode = build_pipeline()

# -----------------------------------------------------------------------------
# Caché con TTL: usa backend.core.cache si existe, si no in-memory
# -----------------------------------------------------------------------------
CACHE_TTL = int(cfg.get("CACHE_TTL_SECONDS", "86400"))

class _MemoryCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self.store: dict[str, tuple[float, dict]] = {}

    async def init(self): ...
    async def get(self, q: str):
        item = self.store.get(q)
        if not item:
            return None
        ts, payload = item
        if time.time() - ts > self.ttl:
            self.store.pop(q, None)
            return None
        return payload

    async def put(self, q: str, answer: str, notes: dict):
        self.store[q] = (time.time(), {"answer": answer, "notes": notes})

try:
    from backend.core.cache import QueryCache as SqlCache
    cache = SqlCache(db_path=SQLITE_DB)
    cache_backend = "sqlite"
except Exception:
    cache = _MemoryCache(ttl=CACHE_TTL)
    cache_backend = "memory"

# -----------------------------------------------------------------------------
# Modelos
# -----------------------------------------------------------------------------
class ChatIn(BaseModel):
    q: str

class ChatOut(BaseModel):
    answer: str
    notes: dict
    citations: list[str] = []

# -----------------------------------------------------------------------------
# Auth simple por API Key (opcional)
# -----------------------------------------------------------------------------
def _require_api_key(request: Request):
    if not SERVER_API_KEY:
        return
    header = request.headers.get("x-api-key") or ""
    if not header:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            header = auth.split(" ", 1)[1].strip()
    if header != SERVER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# -----------------------------------------------------------------------------
# Hooks
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def ensure_boot():
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        await cache.init()
    except Exception:
        pass

    print(f"🚀 N.O.T.A API v{app.version} | ENV={ENV} | MODE={pipeline_mode} | CACHE={cache_backend}")
    print(f"📂 DATA_DIR: {os.path.abspath(DATA_DIR)}")
    print(f"🗃️ SQLITE_DB: {os.path.abspath(SQLITE_DB)} | exists={os.path.exists(SQLITE_DB)}")
    print(f"⭐ Preferidos: {PREFERRED_DOMAINS or '(ninguno)'}")
    print(f"🛡️ TrustedHosts: {TRUSTED_HOSTS or '(no restringido)'} | FORCE_HTTPS={FORCE_HTTPS}")

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    return f"""
    <html>
      <head><meta charset="utf-8"><title>N.O.T.A API</title></head>
      <body style="font-family: -apple-system, system-ui, Segoe UI, Roboto, sans-serif">
        <h1>N.O.T.A API</h1>
        <p>Versión: <b>{app.version}</b> — Entorno: <b>{ENV}</b> — Modo: <b>{pipeline_mode}</b></p>
        <ul>
          <li>GET <code>/health</code></li>
          <li>POST <code>/chat</code> (JSON: <code>{{"q": "tu pregunta"}}</code>)</li>
          <li>GET <code>/chat?q=...</code> (solo prueba)</li>
          {"<li><a href='/docs'>/docs</a></li>" if show_docs else ""}
        </ul>
      </body>
    </html>
    """

@app.get("/favicon.ico")
def favicon():
    return PlainTextResponse("", status_code=204)

@app.get("/health")
def health():
    return {"ok": True, "time": time.time(), "mode": pipeline_mode, "cache": cache_backend}

@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request):
    _require_api_key(request)

    cached = await cache.get(body.q)
    if cached:
        notes = cached["notes"]
        answer = cached["answer"]
        return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

    notes, answer = await pipe.run(body.q)
    await cache.put(body.q, answer, notes)
    return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

@app.get("/chat", response_model=ChatOut)
async def chat_get(q: str, request: Request):
    _require_api_key(request)
    cached = await cache.get(q)
    if cached:
        notes = cached["notes"]
        answer = cached["answer"]
        return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

    notes, answer = await pipe.run(q)
    await cache.put(q, answer, notes)
    return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

@app.get("/debug/env")
def debug_env():
    if ENV != "development" and not show_docs:
        raise HTTPException(status_code=404, detail="Not found")
    def mask(v: Optional[str]):
        if not v or v == "missing":
            return v
        return "set"
    return {
        "ENV": ENV,
        "MODE": pipeline_mode,
        "DATA_DIR": os.path.abspath(DATA_DIR),
        "SQLITE_DB": os.path.abspath(SQLITE_DB),
        "SQLITE_DB_exists": os.path.exists(SQLITE_DB),
        "IOS_FTS_DB": os.path.abspath(IOS_FTS_DB),
        "IOS_FTS_DB_exists": os.path.exists(IOS_FTS_DB),
        "OUTPUT_DB": os.path.abspath(OUTPUT_DB),
        "OUTPUT_DB_exists": os.path.exists(OUTPUT_DB),
        "PREFERRED_DOMAINS": PREFERRED_DOMAINS,
        "ALLOWED_ORIGINS": allow_origins,
        "TRUSTED_HOSTS": TRUSTED_HOSTS,
        "FORCE_HTTPS": FORCE_HTTPS,
        "SERVER_API_KEY_set": bool(SERVER_API_KEY),
    }