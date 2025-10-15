#!/usr/bin/env bash
set -e

echo "🚀 Iniciando N.O.T.A Backend (modo producción)"
echo "📂 DATA_DIR=${DATA_DIR:-/app/backend/data}"

# Crear directorio de datos si no existe
mkdir -p "${DATA_DIR:-/app/backend/data}"

# (Opcional) Descargar tus bases SQLite si están en Firebase Storage
if [ -n "$IOS_FTS_URL" ] && [ ! -f "$DATA_DIR/medical_fts.sqlite" ]; then
  echo "⬇️ Descargando medical_fts.sqlite..."
  curl -L "$IOS_FTS_URL" -o "$DATA_DIR/medical_fts.sqlite" || echo "⚠️ No se pudo descargar medical_fts.sqlite"
fi
if [ -n "$OUTPUT_DB_URL" ] && [ ! -f "$DATA_DIR/output.db" ]; then
  echo "⬇️ Descargando output.db..."
  curl -L "$OUTPUT_DB_URL" -o "$DATA_DIR/output.db" || echo "⚠️ No se pudo descargar output.db"
fi

# Lanzar el servidor
exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2