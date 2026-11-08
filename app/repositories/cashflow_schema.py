"""Normalized Neon DDL for month-1 + multi-month loan cash flows.

Fact tables keep scenario_id (FK → securitization_scenarios) + CF measures only.
Scenario definition fields (cohort, PSA/SDA, PCA/STA, recovery params) live on
securitization_scenarios and are re-exposed via *_enriched views.

CF measures cover three panels:
1. Performing UPB (beg/interest/sched/cpr/cdr/prepay/new default/end)
2. Default roll (beg def / liquidated / recovery / realized loss / end def)
3. Actual cash total (interest+sched+prepay+recovery; defaults ≠ cash)
"""

from __future__ import annotations

LOAN_CF_MONTH1_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS loan_cashflows_month1 (
    scenario_id TEXT NOT NULL REFERENCES securitization_scenarios (scenario_id),
    loan_id TEXT NOT NULL,
    month INTEGER NOT NULL,
    beginning_balance DOUBLE PRECISION,
    interest DOUBLE PRECISION,
    scheduled_principal DOUBLE PRECISION,
    default_amt DOUBLE PRECISION,
    prepay DOUBLE PRECISION,
    recovery DOUBLE PRECISION,
    ending_balance DOUBLE PRECISION,
    loan_age INTEGER,
    cpr DOUBLE PRECISION,
    smm DOUBLE PRECISION,
    cdr DOUBLE PRECISION,
    mdr DOUBLE PRECISION,
    used_recovery_lag_months INTEGER,
    beginning_default_balance DOUBLE PRECISION,
    liquidated_default DOUBLE PRECISION,
    realized_loss DOUBLE PRECISION,
    ending_default_balance DOUBLE PRECISION,
    total_cash DOUBLE PRECISION,
    PRIMARY KEY (scenario_id, loan_id, month)
);
"""

# Idempotent adds for existing Neon tables created before three-panel CF.
LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL = """
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS used_recovery_lag_months INTEGER;
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS beginning_default_balance DOUBLE PRECISION;
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS liquidated_default DOUBLE PRECISION;
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS realized_loss DOUBLE PRECISION;
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS ending_default_balance DOUBLE PRECISION;
ALTER TABLE loan_cashflows_month1
    ADD COLUMN IF NOT EXISTS total_cash DOUBLE PRECISION;
"""

# Back-compat alias name used by older import sites.
LOAN_CF_MONTH1_ADD_USED_LAG_SQL = LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL

LOAN_CF_MONTH1_ENRICHED_VIEW_SQL = """
CREATE OR REPLACE VIEW loan_cashflows_month1_enriched AS
SELECT
    cf.scenario_id,
    cf.loan_id,
    cf.month,
    cf.beginning_balance,
    cf.interest,
    cf.scheduled_principal,
    cf.default_amt,
    cf.default_amt AS new_default,
    cf.prepay,
    cf.recovery,
    cf.ending_balance,
    cf.loan_age,
    cf.cpr,
    cf.smm,
    cf.cdr,
    cf.mdr,
    cf.used_recovery_lag_months,
    cf.beginning_default_balance,
    cf.liquidated_default,
    cf.realized_loss,
    cf.ending_default_balance,
    cf.total_cash,
    s.cohort,
    s.psa_multiple,
    s.sda_multiple,
    CASE s.psa_multiple WHEN 75 THEN 'Down' WHEN 100 THEN 'Base' WHEN 125 THEN 'Up'
         ELSE s.psa_multiple::text END AS pca_level,
    CASE s.sda_multiple WHEN 50 THEN 'Down' WHEN 100 THEN 'Base' WHEN 200 THEN 'Up'
         ELSE s.sda_multiple::text END AS sta_level,
    s.recovery_period_months,
    s.recovery_lag_months,
    s.recovery_rate,
    s.state_varying_recovery_todo,
    s.note AS scenario_note
FROM loan_cashflows_month1 cf
JOIN securitization_scenarios s ON s.scenario_id = cf.scenario_id;
"""

LOAN_MONTH_CF_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS loan_month_cf (
    scenario_id TEXT NOT NULL REFERENCES securitization_scenarios (scenario_id),
    loan_id TEXT NOT NULL,
    month INTEGER NOT NULL,
    beginning_balance DOUBLE PRECISION,
    interest DOUBLE PRECISION,
    scheduled_principal DOUBLE PRECISION,
    default_amt DOUBLE PRECISION,
    prepay DOUBLE PRECISION,
    recovery DOUBLE PRECISION,
    ending_balance DOUBLE PRECISION,
    loan_age INTEGER,
    cpr DOUBLE PRECISION,
    smm DOUBLE PRECISION,
    cdr DOUBLE PRECISION,
    mdr DOUBLE PRECISION,
    used_recovery_lag_months INTEGER,
    beginning_default_balance DOUBLE PRECISION,
    liquidated_default DOUBLE PRECISION,
    realized_loss DOUBLE PRECISION,
    ending_default_balance DOUBLE PRECISION,
    total_cash DOUBLE PRECISION,
    PRIMARY KEY (scenario_id, loan_id, month)
);
"""

LOAN_MONTH_CF_ADD_PANEL_COLS_SQL = """
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS used_recovery_lag_months INTEGER;
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS beginning_default_balance DOUBLE PRECISION;
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS liquidated_default DOUBLE PRECISION;
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS realized_loss DOUBLE PRECISION;
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS ending_default_balance DOUBLE PRECISION;
ALTER TABLE loan_month_cf
    ADD COLUMN IF NOT EXISTS total_cash DOUBLE PRECISION;
"""

LOAN_MONTH_CF_ADD_USED_LAG_SQL = LOAN_MONTH_CF_ADD_PANEL_COLS_SQL

LOAN_MONTH_CF_ENRICHED_VIEW_SQL = """
CREATE OR REPLACE VIEW loan_month_cf_enriched AS
SELECT
    cf.scenario_id,
    cf.loan_id,
    cf.month,
    cf.beginning_balance,
    cf.interest,
    cf.scheduled_principal,
    cf.default_amt,
    cf.default_amt AS new_default,
    cf.prepay,
    cf.recovery,
    COALESCE(cf.realized_loss, cf.default_amt * (1.0 - s.recovery_rate)) AS loss,
    COALESCE(cf.realized_loss, cf.default_amt * (1.0 - s.recovery_rate)) AS realized_loss,
    cf.ending_balance,
    cf.loan_age,
    cf.cpr,
    cf.smm,
    cf.cdr,
    cf.mdr,
    cf.used_recovery_lag_months,
    cf.beginning_default_balance,
    cf.liquidated_default,
    cf.ending_default_balance,
    cf.total_cash,
    s.cohort,
    s.psa_multiple,
    s.sda_multiple,
    CASE s.psa_multiple WHEN 75 THEN 'Down' WHEN 100 THEN 'Base' WHEN 125 THEN 'Up'
         ELSE s.psa_multiple::text END AS pca_level,
    CASE s.sda_multiple WHEN 50 THEN 'Down' WHEN 100 THEN 'Base' WHEN 200 THEN 'Up'
         ELSE s.sda_multiple::text END AS sta_level,
    s.recovery_period_months,
    s.recovery_lag_months,
    s.recovery_rate,
    s.state_varying_recovery_todo,
    s.note AS scenario_note
FROM loan_month_cf cf
JOIN securitization_scenarios s ON s.scenario_id = cf.scenario_id;
"""

MONTH1_FACT_COLS = (
    "scenario_id",
    "loan_id",
    "month",
    "beginning_balance",
    "interest",
    "scheduled_principal",
    "default_amt",
    "prepay",
    "recovery",
    "ending_balance",
    "loan_age",
    "cpr",
    "smm",
    "cdr",
    "mdr",
    "used_recovery_lag_months",
    "beginning_default_balance",
    "liquidated_default",
    "realized_loss",
    "ending_default_balance",
    "total_cash",
)

MONTH1_DROPPED_COLS = (
    "cohort",
    "psa_multiple",
    "sda_multiple",
    "pca_level",
    "sta_level",
)

# Aggregate monthly CF for each of the 27 grid scenarios (no loan grain).
SCENARIO_MONTH_CF_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.scenario_month_cf (
    scenario_id TEXT NOT NULL REFERENCES public.securitization_scenarios (scenario_id),
    month INTEGER NOT NULL,
    interest DOUBLE PRECISION,
    scheduled_principal DOUBLE PRECISION,
    prepay DOUBLE PRECISION,
    new_default DOUBLE PRECISION,
    recovery DOUBLE PRECISION,
    total_cash DOUBLE PRECISION,
    principal_cash DOUBLE PRECISION,
    beginning_balance DOUBLE PRECISION,
    PRIMARY KEY (scenario_id, month)
);
"""

# Idempotent adds for existing Neon tables created before component CF cols.
SCENARIO_MONTH_CF_ADD_COMPONENT_COLS_SQL = """
ALTER TABLE public.scenario_month_cf
    ADD COLUMN IF NOT EXISTS interest DOUBLE PRECISION;
ALTER TABLE public.scenario_month_cf
    ADD COLUMN IF NOT EXISTS scheduled_principal DOUBLE PRECISION;
ALTER TABLE public.scenario_month_cf
    ADD COLUMN IF NOT EXISTS prepay DOUBLE PRECISION;
ALTER TABLE public.scenario_month_cf
    ADD COLUMN IF NOT EXISTS new_default DOUBLE PRECISION;
ALTER TABLE public.scenario_month_cf
    ADD COLUMN IF NOT EXISTS recovery DOUBLE PRECISION;
"""

# WAL + summary per scenario cell and per-cohort AVG of the 9 cells.
COHORT_SCENARIO_WAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.cohort_scenario_wal (
    cohort TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    wal_years DOUBLE PRECISION,
    total_cash_sum DOUBLE PRECISION,
    n_loans INTEGER,
    perform_months INTEGER,
    horizon_months INTEGER,
    PRIMARY KEY (cohort, scenario_id)
);
"""
