# Combined image: Vite React UI + FastAPI on one PORT.
# Runtime stays python:3.12-slim + requirements.txt (pandas included).
# Azure Container Apps injects PORT.

FROM node:20-bookworm-slim AS frontend
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
# Same-origin /api — do not set VITE_API_BASE_URL in this image.
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////data/cashflow.db

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY public ./public
COPY api/README.md ./api/README.md
COPY --from=frontend /ui/dist ./dist

# Prototype SQLite file. Container restart / new revision wipes /data unless a
# volume is mounted there. Override DATABASE_URL with postgres://… for Neon.
RUN mkdir -p /data

EXPOSE 8000
# Shell-form CMD so ${PORT} expands (exec-form JSON does not).
CMD sh -c 'python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'
