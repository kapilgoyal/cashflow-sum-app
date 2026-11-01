# CashFlow Sum App

Vite + React frontend with a Vercel Python serverless function at `api/sum.py`. No FastAPI, no `local-backend/`.

Dense GIC navy / white / pink UI (`THEME.md`). Compact AG Grid sample tape + Recharts cohort chart. Top bar: **CashFlow** + pink `v0.1.0`.

## Theme hexes

| Role | Hex |
| --- | --- |
| Background | `#00204E` |
| Panel / top bar | `#001A3F` |
| Text | `#FFFFFF` |
| Muted text | `#B8C5D6` |
| Accent | `#E85A9B` |
| Accent bright | `#FF6B9D` |

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
├── src/                # React app (AG Grid + Recharts)
├── THEME.md
├── index.html
├── package.json
└── vite.config.js
```
