# Deploy notes

- Railway uses **NIXPACKS** + root `nixpacks.toml` (Python-only) and `railway.toml` start/healthcheck.
- `api.Containerfile` is kept as an optional reference image; do not place a root `Dockerfile` unless Railway Docker builds are verified healthy for this monorepo.
