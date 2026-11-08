# CashFlow assumptions (CSV, not DB)

All modeling assumptions live under repo `data/` as CSV. Neon does **not** store the assumption catalog. The engine bootstraps CSVs on app start (and again on first access via cache).

## Files

| Path | Role |
|------|------|
| `data/assumptions.csv` | Catalog: has_mi, cohort recovery, severity/Fannie paths, PSA/SDA seasoning, sources/URLs |
| `data/urban_freddie_loss_severity_fico_ltv.csv` | Urban/Freddie Table 4 severity by origination year × FICO × LTV + `recovery_rate = 1 − severity` |
| `data/fannie_mae_foreclosure_timeframes.csv` | Fannie state foreclosure days → recovery lag months |

## `has_mi`

- Assumption `has_mi_all=true` (synthetic Minimum Case: everyone has MI).
- **Do not** derive from `monthly_insurance_cost` (hazard/escrow).
- At ASF tape load, `asf_tape.has_mi` is materialized from this CSV flag for all rows.
- Loan CF objects also set `has_mi` from the same assumption.

## Recovery rate

1. If `has_mi` is True → look up Urban Table 4 cell (default vintage band **`2006`**, peak-crisis FICO×LTV) → `recovery_rate = 1 − severity_pct/100`. Falls back within-grid to `fico_band=Total` then `year_band=Total` (LTV-only).
2. If no cell / `has_mi` False → fall back to **cohort** recovery rates in `assumptions.csv` / scenario grid (0.75 / 0.60 / 0.55).

### Severity vintage (explicit — not invented per loan)

The engine does **not** map each loan’s origination year into a severity vintage.
`severity_default_year_band` in `assumptions.csv` (fallback **`2006`**) is a
**deliberate pool-level assumption**: peak-crisis Urban Table 4 severities, used
for all MI loans unless that assumption row is changed. Rationale is also stored
in `data/scenario_config.json` → `mi_credit_recovery.severity_year_rationale`.

Source PDF: [Loss Severity on Residential Mortgages (Goodman & Zhu, Urban Institute, Feb 2015)](https://www.urban.org/sites/default/files/publication/39566/2000092-Loss-Severity-on-Residential-Mortgages.pdf) — Table 4. Agency collateral; LTV > 80 severities reflect MI.

## PSA / SDA seasoning

Documented in `assumptions.csv` (`psa_seasoning_rule`, `sda_seasoning_rule`) and implemented in `app/services/psa_prepay.py` / `sda_default.py`:

- PSA: 0.2% × age through month 30, then 6% CPR (× multiple/100).
- SDA: ramp to 0.60% CDR by month 30, flat to 60, decline to 0.03% by 120, then flat (× multiple/100).

Materialized month paths for the Scenarios side charts live in `data/psa_sda_standards.csv` (mirrored to `public/psa_sda_standards.csv`). Regenerate with `scripts/generate_psa_sda_standards.py`.

## UI / API

- Nav tab **Assumptions** — AG Grid of each `assumptions.csv` row (value, path, source name, URL, notes).
- `GET /api/assumptions` — same catalog JSON.
- `POST /api/assumptions/reload` — re-read CSVs after edits.
