# ---- 1. Compilación del frontend ----
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Imagen final ----
FROM python:3.12-slim

# ffmpeg hace todo el trabajo de vídeo; las fuentes dibujan los subtítulos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        fonts-liberation2 \
        libgl1 \
        libglib2.0-0 \
    # Inter no está en todas las ramas de Debian; si falta, libass usa otra.
    && (apt-get install -y --no-install-recommends fonts-inter \
        || echo "AVISO: Inter no disponible, los subtítulos usarán la fuente del sistema") \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/backend/viralclips/static ./backend/viralclips/static

# El modelo de caras (230 KB) se descarga durante la construcción.
RUN python backend/scripts/fetch_models.py || \
    echo "AVISO: sin modelo de caras; el reencuadre usará saliencia por movimiento"

ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "viralclips.main:app", "--host", "0.0.0.0", "--port", "8000"]
