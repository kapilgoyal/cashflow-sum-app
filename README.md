# CashFlow Sum App

Vite + React frontend with a Vercel Python serverless function at `api/sum.py`, plus a local FastAPI-oriented Python package under `app/` for securitization scenario grids and one-loan cash flows.

Dense GIC navy / white / pink UI (`THEME.md`). Compact AG Grid sample tape + Recharts cohort chart. Top bar: **CashFlow** + pink `v0.1.0`.

## Theme hexes

| Role | Hex |
| --- | --- |
| Background | `#00204E` |
| Panel / top bar | `#001A3F` |
| Text | `#FFFFFF` |
| Muted text | `#B8C5D6` |
| Accent | `#E85A9B` |
| Accent bright | `#FF6B9D` |

## Securitization engine (`app/`)

SOLID-ish layout:

- `app/models` — `Loan`, `Scenario`, `CashflowRow` (Pydantic)
- `app/services` — PSA/SDA curves, scenario grid, one-loan CF engine
- `app/repositories` — Excel tape + scenario CSV / optional Neon seed
- `app/main.py` — minimal FastAPI (`/health`, `/scenarios`, `/cashflows/sample`)

```bash
# from repo root, with nqm-cashflow or any env that has requirements.txt
pip install -r requirements.txt
python scripts/generate_scenario_and_cf.py
uvicorn app.main:app --reload
```

### Scenario grid

- Cohorts: `low LTV and weak refinance incentive`, `high LTV and strong refinance incentive`, `high LTV and weak refinance incentive`
- PSA (PCA) Down/Base/Up: **75 / 100 / 125** (base case = **100 PSA**)
- SDA (STA) Down/Base/Up: **50 / 100 / 200**
- Full cross = **27 rows** in `data/securitization_scenarios.csv`
- Recovery (per cohort, lag=0): strong-incentive high-LTV **60%/12mo**; weak-incentive high-LTV **55%/15mo**; weak-incentive low-LTV **75%/9mo** (state-varying lag TODO)

### One-loan CF sample

`scripts/generate_scenario_and_cf.py` picks the first Fixed loan from `Minimum_Case.xlsx` and projects months 1..360 at **100 PSA / 100 SDA** (first-cohort base cell). Output: `data/one_loan_cf_sample.csv`.

### TODO — state-varying recovery / foreclosure lag

**Not implemented.** Recovery period and lag are pool-level constants. Future work: map `STATE` → foreclosure / REO timeline and vary `recovery_lag_months` (and possibly recovery period) by jurisdiction. The scenario CSV / SQL schema flags this with `state_varying_recovery_todo=true` and a note column.

Optional Neon seed: set `DATABASE_URL`; the generator attempts insert into `securitization_scenarios` and skips cleanly if unreachable.

## Deploy (Vercel)

1. Import the repo as a **single** Vite project (not multi-service).
2. No `vercel.json` required — Vercel serves `api/*.py` automatically.

## Local frontend

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). `/api/sum` only works on Vercel (or with a local Vercel CLI); the UI POSTs there and displays the JSON `sum`.

## Layout

```
.
├── api/
│   └── sum.py              # Vercel Python serverless (GET/POST → {sum})
├── app/                    # FastAPI-ready CF engine (models/services/repositories)
├── data/                   # scenarios + one-loan CF CSVs
├── docs/data/              # mirrored tape + CF outputs
├── scripts/
│   ├── export_cluster_tape.py
│   └── generate_scenario_and_cf.py
├── src/                    # React app (AG Grid + Recharts)
├── requirements.txt
├── THEME.md
├── index.html
├── package.json
└── vite.config.js
```
