# Legacy Vercel Mangum entry (retired)

These files used to power `api/index.py` on Vercel. Production hit the **225 MB** serverless bundle limit (pandas/numpy/etc.).

Use Railway always-on `uvicorn` instead (`Procfile`, `railway.toml`). Keep this folder only as historical reference.
