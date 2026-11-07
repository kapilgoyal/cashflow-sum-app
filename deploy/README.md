# Deploy notes

- **Azure Container App (only)** — one app serves Vite + FastAPI from the root `Dockerfile`.
- **GHCR** — `.github/workflows/azure-proto-ghcr.yml` builds and pushes `ghcr.io/kapilgoyal/cashflow-sum-app:proto` (+ SHA tag) on `master`. Import into `cashflowacr` and roll the Container App when ACR Tasks is unavailable (see [azure.md](./azure.md)).
- **OIDC → ACR** — `.github/workflows/azure-container-app.yml` builds, pushes to ACR, and updates the Container App once the six `AZURE_*` secrets exist. Portal steps: [azure.md](./azure.md).
- Optional: `api.Containerfile` as an API-only reference image (not used in production).
- `deploy/legacy-vercel-mangum/` is historical only — not in the active path.

## SQLite prototype database

The image defaults `DATABASE_URL=sqlite:////data/cashflow.db` and `mkdir`s `/data`. FastAPI bootstraps schema + the Minimum Case tape when the file is missing or `asf_tape` is empty.

**Restart / new revision wipes that file** unless you mount a volume at `/data`. Azure Container Apps Consumption disks are ephemeral. For the prototype that is OK (boot reloads the tape from `data/Minimum_Case.xlsx`).

Set sqlite explicitly (container or local):

```bash
# container (matches Dockerfile ENV)
DATABASE_URL=sqlite:////data/cashflow.db

# local, repo-relative
DATABASE_URL=sqlite:///./data/cashflow.db

# local, absolute
DATABASE_URL=sqlite:////tmp/cashflow.db
```

Keep Neon by setting a `postgres://` or `postgresql://` `DATABASE_URL` on the Container App (not in GitHub). Optional `DATABASE_URL_UNPOOLED` is still used for bulk writes.
