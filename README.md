# Sum App

Minimal Vite + React frontend with a Python serverless `/api/sum` endpoint.

Single-project layout for Vercel (Vite at repo root + `api/sum.py`). No multi-service `frontend/` + `backend/` folders.

## Deploy (Vercel)

Import this GitHub repo as a **single** project. Cancel any multi-service import suggestion and Import again after this layout change.

- Framework: Vite (auto-detected)
- Serverless API: `api/sum.py` → `/api/sum`
- No `vercel.json` required

## Local frontend

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). In production on Vercel, `/api/sum` is served by `api/sum.py`. For local API during `npm run dev`, either:

1. Point the Vite proxy at a local FastAPI process (see below), or
2. Deploy / use `vercel dev` so `api/sum.py` is available.

## Local-only FastAPI (optional)

`local-backend/` is **not** deployed. It is a convenience FastAPI server for local development only (kept out of the `backend/` name so Vercel does not detect a FastAPI service).

```bash
cd local-backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Then run the frontend from the repo root (`npm run dev`). The Vite proxy forwards `/api` to port 8000.

- `GET /api/sum?a=2&b=3` → `{"sum":5.0}`
- `POST /api/sum` with JSON `{"a":2,"b":3}` → `{"sum":5.0}`

## Layout

```
.
├── api/
│   └── sum.py          # Vercel Python serverless function
├── local-backend/      # optional local FastAPI only (not for Vercel)
├── src/                # React app
├── index.html
├── package.json
└── vite.config.js
```
