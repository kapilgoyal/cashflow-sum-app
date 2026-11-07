# Always-on FastAPI for Railway. Pure Python — ignore Vite/Node in this image.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/cashflow.db

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY api/README.md ./api/README.md

# Prototype SQLite file. Container restart / new revision wipes /data unless a
# volume is mounted there. Override DATABASE_URL with postgres://… for Neon.
# Same /data default applies to the Azure one-container image (PR #30).
RUN mkdir -p /data

# Railway injects PORT. Shell-form CMD so ${PORT} expands (exec-form JSON
# with a bare $PORT does not).
EXPOSE 8000
CMD sh -c 'python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'
