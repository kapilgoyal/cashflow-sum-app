# Deploy notes

- **Azure (cutover path)** — one Container App serves Vite + FastAPI from the root `Dockerfile`. Workflow `.github/workflows/azure-container-app.yml`. Portal steps + secrets: [azure.md](./azure.md). Do not tear down Vercel/Railway until Azure is healthy.
- **Railway API** — same root `Dockerfile` (now also embeds the UI) + `railway.toml` (`watchPatterns`, shell `startCommand`, `/health`).
- **GitHub → master** — deploy only Railway project **`kind-emotion`** via `.github/workflows/railway-deploy.yml` + secret **`RAILWAY_TOKEN`** (Project Token from kind-emotion). Disconnect crashed `beautiful-tranquility` / `patient-illumination` from this repo.
- Optional: `api.Containerfile` as an API-only reference image.
- Vercel hosts the Vite UI only until cutover; set build env `VITE_API_BASE_URL` to the Railway origin.
