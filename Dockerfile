# ── Stage 1: build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=server.settings \
    PORT=8000

WORKDIR /app

# Minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Copy compiled React bundle into Django's static_react dir
RUN mkdir -p /app/server/static_react
COPY --from=web /web/dist /app/server/static_react/

# Copy sample CSVs into image so demo can ingest from them
COPY samples/ /app/samples/

# Prepare data volume mount point
RUN mkdir -p /data /app/staticfiles

EXPOSE 8000

# Entrypoint: migrate, seed, collectstatic, then start gunicorn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:8000/api/health/ || exit 1

CMD ["/entrypoint.sh"]
