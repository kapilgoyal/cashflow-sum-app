# Deploy notes

- **Railway API** — root `Dockerfile` (shell-form `CMD` with `${PORT}`) + `railway.toml` (`watchPatterns`, shell `startCommand`, `/health`).
- **GitHub → master** — deploy only Railway project **`kind-emotion`** via `.github/workflows/railway-deploy.yml` + secret **`RAILWAY_TOKEN`** (Project Token from kind-emotion). Disconnect crashed `beautiful-tranquility` / `patient-illumination` from this repo.
- Optional: `api.Containerfile` as a reference image copy.
- Vercel hosts the Vite UI only; set build env `VITE_API_BASE_URL` to the Railway origin.

## SQLite prototype database

The image defaults `DATABASE_URL=sqlite:////data/cashflow.db` and `mkdir`s `/data`. FastAPI bootstraps schema + the Minimum Case tape when the file is missing or `asf_tape` is empty.

**Restart / new revision wipes that file** unless you mount a volume at `/data`. Azure Container Apps Consumption and Railway disks are ephemeral. For the prototype that is OK (boot reloads the tape from `data/Minimum_Case.xlsx`).

Set sqlite explicitly (container or local):

```bash
# container (matches Dockerfile ENV)
DATABASE_URL=sqlite:////data/cashflow.db

# local, repo-relative
DATABASE_URL=sqlite:///./data/cashflow.db

# local, absolute
DATABASE_URL=sqlite:////tmp/cashflow.db
```

Keep Neon by setting a `postgres://` or `postgresql://` `DATABASE_URL` on the service (not in GitHub). Optional `DATABASE_URL_UNPOOLED` is still used for bulk writes.

The Azure one-container PR (#30) should keep the same `/data` default: add `ENV DATABASE_URL=sqlite:////data/cashflow.db` and `RUN mkdir -p /data` to that multi-stage Dockerfile (it already `COPY data ./data`, which includes `Minimum_Case.xlsx`). No Azure credentials are stored in this repo.
