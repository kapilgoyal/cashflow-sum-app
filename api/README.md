# Legacy serverless entry (retired)

This folder is not part of the active deploy path. Production is a single Azure Container App image from the root `Dockerfile` (UI + FastAPI).

Historical Mangum / Vercel Python entrypoints live under `deploy/legacy-vercel-mangum/` for reference only.

Do **not** add `*.py` files here — unused by Azure, and would only confuse old platform scanners.
