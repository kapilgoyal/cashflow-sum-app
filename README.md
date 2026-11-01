# Sum App

Minimal **Vite + React** frontend with a Vercel Python serverless function at `api/sum.py`. No FastAPI, no `local-backend/`.

> **Vercel:** Import as a **single** Vite project. The `api/` folder is Vercel’s Python runtime (BaseHTTPRequestHandler), not a separate FastAPI root.

## Deploy (Vercel)

1. Import the repo as a **single** Vite project (not multi-service).
2. No `vercel.json` required — Vercel serves `api/*.py` automatically.

## Local frontend

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). `/api/sum` only works on Vercel (or with a local Vercel CLI); the UI POSTs there and displays the JSON `sum`.

## Layout

```
.
├── api/
│   └── sum.py          # Vercel Python serverless (GET/POST → {sum})
├── src/                # React app
├── index.html
├── package.json
└── vite.config.js
```
