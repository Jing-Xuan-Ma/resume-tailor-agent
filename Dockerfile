# ── Stage 1: build frontend (standalone) ──────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /build

ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ .
RUN mkdir -p public
RUN npm run build

# ── Stage 2: all-in-one runtime ───────────────────────────────────
FROM python:3.12-slim

# weasyprint shared libs + nodejs + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libharfbuzz0b \
      libcairo2 \
      libgdk-pixbuf-2.0-0 \
      libffi-dev \
      shared-mime-info \
      supervisor \
      curl \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend deps (COPY README to satisfy pyproject readme= field)
COPY README.md /app/backend/README.md
COPY backend/pyproject.toml /app/backend/pyproject.toml
WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

COPY backend/ /app/backend/

# Frontend: standalone server + static assets
COPY --from=frontend-builder /build/.next/standalone /app/frontend
COPY --from=frontend-builder /build/.next/static /app/frontend/.next/static
COPY --from=frontend-builder /build/public /app/frontend/public/

RUN mkdir -p /app/backend/data

COPY supervisord.conf /etc/supervisor/conf.d/app.conf

EXPOSE 3000 8000
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/app.conf"]
