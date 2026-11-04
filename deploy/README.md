# Deploy notes

- **Railway API** — root `Dockerfile` (shell-form `CMD` with `${PORT}`) + `railway.toml` (`watchPatterns`, shell `startCommand`, `/health`).
- **GitHub → master** — Railway Source auto-deploy when connected; CI backup via `.github/workflows/railway-deploy.yml` using secret **`RAILWAY_TOKEN`** (exact name).
- Optional: `api.Containerfile` as a reference image copy.
- Vercel hosts the Vite UI only; set build env `VITE_API_BASE_URL` to the Railway origin.
