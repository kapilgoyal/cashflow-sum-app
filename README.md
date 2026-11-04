# CashFlow Sum App

Vite + React professional light frontend (white content, `#001A41` type) with a local FastAPI package under `app/` for securitization scenario grids and month-1 cohort cash flows.

Left nav: **Loan** · **Cash Flow Scenarios** · **Cash Flow**. In-memory scenario results (no full reload). Top bar: **CashFlow** + amber `v0.2.0`.

## Securitization engine (`app/`)

SOLID-ish layout:

- `app/models` — `Loan`, `Scenario`, `CashflowRow` (Pydantic)
- `app/services` — PSA/SDA curves, scenario grid, one-loan CF engine
- `app/repositories` — Excel tape + scenario CSV / optional Neon seed
- `app/main.py` — minimal FastAPI (`/health`, `/scenarios`, `/cashflows/sample`)

```bash
# from repo root
pip install -r requirements.txt
python scripts/run_27_month1_parallel.py
uvicorn app.main:app --reload
```

### Scenario grid

- Cohorts (no "RI" in labels): `high LTV and strong refinance incentive`, `high LTV and weak refinance incentive`, `low LTV and weak refinance incentive`
- PSA (PCA) Down/Base/Up: **75 / 100 / 125**
- SDA (STA) Down/Base/Up: **50 / 100 / 200**
- Full cross = **27 rows** in `data/securitization_scenarios.csv`
- Recovery **rate**: when `has_mi` (from `data/assumptions.csv`, synthetic → **true** for all loans) use Urban/Freddie Table 4 severity grid → `recovery = 1 − severity` (`data/urban_freddie_loss_severity_fico_ltv.csv`); else fall back to cohort rates (high-LTV strong **60%/12mo**; high-LTV weak **55%/15mo**; low-LTV weak **75%/9mo**).
- Recovery **lag**: Fannie Mae state foreclosure time frames in `data/fannie_mae_foreclosure_timeframes.csv` (source: https://singlefamily.fanniemae.com/media/6726/display); `used_recovery_lag_months ≈ days/30`. Scenario `recovery_lag_months` is fallback only when state is unknown.
- **Assumptions** (CSV, not DB): `data/assumptions.csv` + nav tab **Assumptions** / `GET /api/assumptions` — has_mi, severity & Fannie paths, cohort recovery, PSA/SDA seasoning, source URLs. See `docs/assumptions.md`.
- CF rows cover three panels: performing UPB, default roll (lag liquidation → recovery + realized loss), actual cash (`total_cash`; defaults ≠ cash). See store `docs/cf-panel-refs/` and `docs/recovery-rate-benchmarks.md`.

### Month-1 parallel run

`scripts/run_27_month1_parallel.py` runs **one month** for every loan in each scenario's cohort via `ProcessPoolExecutor(max_workers=27)`. Loan-level CF → Neon when `DATABASE_URL` is set; else SQLite + JSON under `data/`. Cohort aggregates → `data/cohort_month1_cf.json` (+ `public/cohort-month1.json` for the UI).

Optional Neon seed: set `DATABASE_URL`; scripts attempt insert and skip cleanly if unset/unreachable.

## Deploy (durable)

**Frontend (static)** — Vercel  
**API (always-on)** — Railway (`uvicorn app.main:app`, see `Procfile` / `railway.toml`)

Vercel no longer runs Python serverless (Mangum retired under `deploy/legacy-vercel-mangum/`). That avoided the 225 MB function size ceiling.

### Railway (FastAPI)

1. Create a Railway project from this repo (Dockerfile / Nixpacks; `railway.toml` watches `app/**`).
2. Connect GitHub → branch **`master`** with auto-deploy enabled (Railway → Settings → Source).
3. Set env vars on the Railway service (never commit them):
   - `DATABASE_URL` — Neon pooled Postgres URL
   - `DATABASE_URL_UNPOOLED` — optional Neon direct URL
4. **CI (kind-emotion only):** ignore crashed Railway projects `beautiful-tranquility` / `patient-illumination` (disconnect them from this GitHub repo).  
   - Railway → project **`kind-emotion`** → Settings → Tokens → Project Token  
   - GitHub → Settings → Secrets → Actions → Name (exact): **`RAILWAY_TOKEN`**  
   - Optional: **`RAILWAY_SERVICE_ID`** for the service behind `cashflow-sum-app-production.up.railway.app`  
   - Workflow [`.github/workflows/railway-deploy.yml`](.github/workflows/railway-deploy.yml) runs `railway up --ci` on every push to `master`.
5. Public API: `https://cashflow-sum-app-production.up.railway.app` (service in **kind-emotion**).
6. Health: `GET /health`. Dockerfile / `railway.toml` start commands use shell form so `${PORT}` expands.


### Vercel (React)

1. Build is Vite → `dist/` (`vercel.json` SPA rewrite only; no `/api` Python).
2. Set **build** env `VITE_API_BASE_URL` to the Railway origin (no trailing slash), e.g. `https://<service>.up.railway.app`.
3. Redeploy so the client embeds that base (`src/apiBase.js`).
4. UI: https://cashflow-sum-app.vercel.app

### Local

```bash
# API
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# UI (proxies /api → :8000)
npm install && npm run dev
```

Left nav: **Investor Tape** · **Loan QC** · **Stratification** · **Cohort** · **Scenarios** · **Cash Flow** · **Assumptions**.  
**Run month 1** → `POST /api/cashflows/run-month1` (Neon when `DATABASE_URL` is set).

## Local frontend

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). Vite proxies `/api` to `uvicorn` on `:8000`.

## Layout

```
.
├── app/                    # FastAPI CF engine
├── data/                   # scenarios + month-1 CF (SQLite/JSON)
├── docs/data/              # mirrored outputs
├── scripts/
│   ├── export_cluster_tape.py
│   └── run_27_month1_parallel.py
├── src/                    # React (Loan / Scenarios / Cash Flow)
├── requirements.txt
└── vite.config.js
```
