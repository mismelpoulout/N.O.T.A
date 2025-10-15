# backend/app.py
import os
import time
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import dotenv_values

# Internos
from backend.core.pipeline import NOTAPipeline
from backend.core.search_client import SearchClient

# -----------------------------------------------------------------------------
# Config (.env + entorno)
# -----------------------------------------------------------------------------
cfg = {**dotenv_values("backend/.env"), **os.environ}

DATA_DIR = cfg.get("DATA_DIR", "./backend/data")
ALLOWED = cfg.get("ALLOWED_ORIGINS", "*")
TRUSTED_HOSTS = [h.strip() for h in (cfg.get("TRUSTED_HOSTS") or "").split(",") if h.strip()]
FORCE_HTTPS = (cfg.get("FORCE_HTTPS", "false").lower() in ("1", "true", "yes"))
ENV = (cfg.get("ENV") or "production").lower()          # "development" | "production"
SERVER_API_KEY = cfg.get("SERVER_API_KEY")              # opcional, para proteger /chat

# Bases locales (opcional)
IOS_FTS_DB = cfg.get("IOS_FTS_DB", f"{DATA_DIR.rstrip('/')}/medical_fts.sqlite")
OUTPUT_DB = cfg.get("OUTPUT_DB", f"{DATA_DIR.rstrip('/')}/output.db")

# Dominios preferidos (ranking/búsqueda priorizada)
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
    version="0.5",
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None,
)

# Middlewares
allow_origins = ["*"] if ALLOWED == "*" else [o.strip() for o in ALLOWED.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    # ✅ FIX: lista válida (o simplemente ["*"])
    allow_headers=["*", "Authorization", "X-API-Key"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)

if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

if FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)

# Search client
search_client = SearchClient.from_env(cfg)

# Pipeline principal
pipe = NOTAPipeline(
    db_dir=DATA_DIR,
    search_client=search_client,
    ios_fts_db=IOS_FTS_DB,
    output_db=OUTPUT_DB,
    preferred_domains=PREFERRED_DOMAINS,
)

# -----------------------------------------------------------------------------
# Modelos
# -----------------------------------------------------------------------------
class ChatIn(BaseModel):
    q: str

class ChatOut(BaseModel):
    answer: str
    notes: dict
    citations: list[str]

# -----------------------------------------------------------------------------
# Aux: auth simple por API Key (opcional)
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
async def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    engine = (cfg.get("SEARCH_ENGINE") or "").upper()
    print(f"🔍 SEARCH_ENGINE={engine or 'NONE'} | client={'OK' if search_client else 'NONE'}")
    print(f"📂 DATA_DIR: {os.path.abspath(DATA_DIR)}")
    print(f"🗃️ IOS_FTS_DB: {os.path.abspath(IOS_FTS_DB)} | exists={os.path.exists(IOS_FTS_DB)}")
    print(f"🗃️ OUTPUT_DB:  {os.path.abspath(OUTPUT_DB)} | exists={os.path.exists(OUTPUT_DB)}")
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
        <p>Versión: <b>{app.version}</b> — Entorno: <b>{ENV}</b></p>
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
    return {"ok": True, "time": time.time()}

@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request):
    _require_api_key(request)
    notes, answer = await pipe.run(body.q)
    return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

# GET de prueba rápida desde navegador
@app.get("/chat", response_model=ChatOut)
async def chat_get(q: str, request: Request):
    _require_api_key(request)
    notes, answer = await pipe.run(q)
    return ChatOut(answer=answer, notes=notes, citations=notes.get("citations", []))

# Diagnóstico (solo dev o si ENABLE_DOCS=true)
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
        "SEARCH_ENGINE": cfg.get("SEARCH_ENGINE"),
        "GOOGLE_API_KEY": mask(cfg.get("GOOGLE_API_KEY")),
        "GOOGLE_CX": cfg.get("GOOGLE_CX"),
        "BING_KEY": mask(cfg.get("BING_KEY")),
        "DATA_DIR": os.path.abspath(DATA_DIR),
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

@app.get("/search/test")
async def search_test(q: str, n: int = 5):
    if not search_client:
        return {"ok": False, "error": "search_client no configurado", "items": []}
    try:
        hits = await search_client.search(q, count=n)
    except Exception as e:
        return {"ok": False, "error": str(e), "items": []}
    return {"ok": True, "count": len(hits or []), "items": (hits or [])[:n]}