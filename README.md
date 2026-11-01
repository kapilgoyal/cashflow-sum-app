# Sum App

Minimal **Vite + React** app at the repo root. Sum runs in the browser — no Python/FastAPI in this repo.

> **Vercel:** This repo is Vite-only. Local FastAPI / `api/` serverless helpers were removed so Vercel does not detect a multi-service (FastAPI + Vite) project. Import as a **single** Vite project.

## Deploy (Vercel)

1. Cancel any multi-service import if Vercel suggests one.
2. Choose **Import single project** / framework **Vite**, or re-import the repo after this push.
3. No `vercel.json` required.

## Local

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

## Layout

```
.
├── src/                # React app
├── index.html
├── package.json
└── vite.config.js
```
