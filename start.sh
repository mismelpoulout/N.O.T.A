#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Iniciando N.O.T.A Backend (modo producción)"
echo "📂 DATA_DIR=${DATA_DIR:-./backend/data}"
echo "🐍 Python: $(python3 --version 2>/dev/null || echo 'no detectado')"
echo "💬 LLM: ${LLM_MODEL:-no configurado} @ ${LLM_BASE_URL:-desconocido}"

# ------------------------------------------------------
# Crear directorio de datos si no existe
# ------------------------------------------------------
mkdir -p "${DATA_DIR:-./backend/data}"

# ------------------------------------------------------
# Descargar bases SQLite (si las URLs están configuradas)
# ------------------------------------------------------
if [ -n "${GCS_MEDICAL_FTS_URL:-}" ] && [ ! -f "$DATA_DIR/medical_fts.sqlite" ]; then
  echo "⬇️ Descargando medical_fts.sqlite..."
  curl -fsSL "$GCS_MEDICAL_FTS_URL" -o "$DATA_DIR/medical_fts.sqlite" || echo "⚠️ No se pudo descargar medical_fts.sqlite"
fi

if [ -n "${GCS_OUTPUT_DB_URL:-}" ] && [ ! -f "$DATA_DIR/output.db" ]; then
  echo "⬇️ Descargando output.db..."
  curl -fsSL "$GCS_OUTPUT_DB_URL" -o "$DATA_DIR/output.db" || echo "⚠️ No se pudo descargar output.db"
fi

# ------------------------------------------------------
# Verificación de Ollama local (si se usa LLM_BASE_URL)
# ------------------------------------------------------
if [[ "${LLM_BASE_URL:-}" == "http://127.0.0.1:11434/v1" ]]; then
  if ! curl -s http://127.0.0.1:11434/api/version >/dev/null; then
    echo "⚠️ Ollama no está corriendo en 127.0.0.1:11434"
  else
    echo "✅ Ollama detectado (http://127.0.0.1:11434)"
    if [ -n "${LLM_MODEL:-}" ]; then
      if ! ollama list | grep -q "$LLM_MODEL"; then
        echo "⬇️ Descargando modelo $LLM_MODEL..."
        ollama pull "$LLM_MODEL" || echo "⚠️ No se pudo descargar el modelo $LLM_MODEL"
      else
        echo "✅ Modelo $LLM_MODEL disponible localmente"
      fi
    fi
  fi
fi

# ------------------------------------------------------
# Activar entorno virtual si existe
# ------------------------------------------------------
if [ -d ".venv312" ]; then
  echo "📦 Activando entorno virtual .venv312..."
  source .venv312/bin/activate
fi

# ------------------------------------------------------
# Lanzar el servidor
# ------------------------------------------------------
echo "🚀 Lanzando Uvicorn..."
exec uvicorn backend.app:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 2 \
  --proxy-headers \
  --forwarded-allow-ips="*" \
  --timeout-keep-alive 65