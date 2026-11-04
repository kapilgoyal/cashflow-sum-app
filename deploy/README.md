# Deploy notes

- **Railway API** — root `Dockerfile` (shell-form `CMD` with `${PORT}`) + `railway.toml` (`watchPatterns`, shell `startCommand`, `/health`).
- **GitHub → master** — deploy only Railway project **`kind-emotion`** via `.github/workflows/railway-deploy.yml` + secret **`RAILWAY_TOKEN`** (Project Token from kind-emotion). Disconnect crashed `beautiful-tranquility` / `patient-illumination` from this repo.
- Optional: `api.Containerfile` as a reference image copy.
- Vercel hosts the Vite UI only; set build env `VITE_API_BASE_URL` to the Railway origin.
