# CashFlow Sum App

Vite + React Bloomberg-themed frontend with a local FastAPI package under `app/` for securitization scenario grids and month-1 cohort cash flows.

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

## Deploy (Vercel)

1. Vite frontend (`dist/`) + FastAPI via Mangum at `api/index.py`.
2. `vercel.json` rewrites `/api/*` → Mangum and SPA routes → `index.html`.
3. Set `DATABASE_URL` (and ideally `DATABASE_URL_UNPOOLED`) in the Vercel project env.
4. Left nav: **ASF Tape** · **Loan QC** · **Stratification** · **Cohort** · **Scenarios** · **Cash Flow** · **Assumptions**.
5. **Run month 1** → `POST /api/cashflows/run-month1` (loads Neon cache on Vercel; full engine locally; persists loan-level CF).

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
