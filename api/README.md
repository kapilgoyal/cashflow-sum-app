# Legacy Vercel Python serverless (retired)

Production no longer runs FastAPI via Mangum on Vercel (225 MB function limit).

- Always-on API: Railway (`Procfile` / `railway.toml`) — `uvicorn app.main:app`
- Static UI: Vercel (Vite `dist/`) with `VITE_API_BASE_URL` pointing at the Railway host

The previous Mangum entrypoints live under `deploy/legacy-vercel-mangum/` for reference only.
Do **not** add `*.py` files here — Vercel would treat them as serverless functions again.
