"""Normalized Neon DDL for month-1 + multi-month loan cash flows.

Fact tables keep scenario_id (FK → securitization_scenarios) + CF measures only.
Scenario definition fields (cohort, PSA/SDA, PCA/STA, recovery params) live on
securitization_scenarios and are re-exposed via *_enriched views.
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
    PRIMARY KEY (scenario_id, loan_id, month)
);
"""

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
    cf.prepay,
    cf.recovery,
    cf.ending_balance,
    cf.loan_age,
    cf.cpr,
    cf.smm,
    cf.cdr,
    cf.mdr,
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
    PRIMARY KEY (scenario_id, loan_id, month)
);
"""

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
    cf.prepay,
    cf.recovery,
    (cf.default_amt * (1.0 - s.recovery_rate)) AS loss,
    cf.ending_balance,
    cf.loan_age,
    cf.cpr,
    cf.smm,
    cf.cdr,
    cf.mdr,
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
)

MONTH1_DROPPED_COLS = (
    "cohort",
    "psa_multiple",
    "sda_multiple",
    "pca_level",
    "sta_level",
)
