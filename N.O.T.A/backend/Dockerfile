# Usa Python estable para FastAPI
FROM python:3.11-slim

# Variables de entorno base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar dependencias primero
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# Copiar todo el proyecto
COPY . /app

# Crear directorio de datos (para tus SQLite)
RUN mkdir -p /app/backend/data

# Puerto usado por FastAPI (Render o Fly usan $PORT)
ENV PORT=8000

# Script de arranque (lo veremos abajo)
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Comando por defecto
CMD ["/bin/sh", "/app/start.sh"]