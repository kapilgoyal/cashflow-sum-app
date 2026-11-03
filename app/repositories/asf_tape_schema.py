"""DDL for public.asf_tape + QC check/result tables (no CF / scenario tables)."""

from __future__ import annotations

ASF_TAPE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.asf_tape (
    loan_id                               text PRIMARY KEY,
    cutoff_date                           date,
    current_loan_amount                   double precision,
    current_interest_rate                 double precision,
    current_payment_amount_due            double precision,
    remaining_term                        integer,
    amortization_type                     text,
    remaining_io_months                   integer,
    loan_age_months                       integer,
    origination_date                      date,
    original_loan_amount                  double precision,
    original_appraised_property_value     double precision,
    most_recent_property_value            double precision,
    lien_position                         integer,
    senior_lien_current_balance           double precision,
    junior_lien_balance                   double precision,
    original_ltv                          double precision,
    original_cltv                         double precision,
    original_fico                         integer,
    state                                 text,
    postal_code                           text,
    property_type                         text,
    occupancy                             text,
    loan_purpose                          text,
    documentation_type                    text,
    tila_status                           text,
    business_purpose_flag                 text,
    originator_dti                        double precision,
    dscr                                  double precision,
    days_delinquent                       integer,
    liquid_cash_reserves                  double precision,
    prepayment_penalty_remaining_term     integer,
    arm_initial_fixed_months              integer,
    arm_reset_frequency_months            integer,
    arm_index                             text,
    arm_gross_margin                      double precision,
    arm_initial_cap                       double precision,
    arm_periodic_cap                      double precision,
    arm_lifetime_cap                      double precision,
    arm_lifetime_floor                    double precision,
    monthly_property_tax                  double precision,
    monthly_insurance_cost                double precision,
    monthly_hoa_cost                      double precision,
    pitia                                 double precision,
    rental_income_used_for_dscr           double precision,
    refinance_incentive                   double precision,
    cohort                                text,
    has_mi                                boolean NOT NULL DEFAULT true,
    loaded_at                             timestamptz NOT NULL DEFAULT now()
);
"""

# Idempotent add for DBs created before has_mi existed (nullable first so IF NOT EXISTS is safe).
ASF_TAPE_HAS_MI_ALTER_SQL = """
ALTER TABLE public.asf_tape
    ADD COLUMN IF NOT EXISTS has_mi boolean DEFAULT true;
"""

# Backfill nulls after ADD COLUMN (existing rows stay NULL without this).
ASF_TAPE_HAS_MI_BACKFILL_SQL = """
UPDATE public.asf_tape
SET has_mi = true
WHERE has_mi IS NULL;
"""

# Enforce DEFAULT true NOT NULL once every row is non-null.
ASF_TAPE_HAS_MI_NOT_NULL_SQL = """
ALTER TABLE public.asf_tape
    ALTER COLUMN has_mi SET DEFAULT true,
    ALTER COLUMN has_mi SET NOT NULL;
"""

QC_CHECKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.qc_checks (
    check_id          text PRIMARY KEY,
    source            text NOT NULL,
    edit_number       integer,
    nl_description    text NOT NULL,
    sql_predicate     text,
    required_columns  text[] NOT NULL DEFAULT '{}',
    status_mode       text NOT NULL DEFAULT 'active',
    skip_reason       text,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
"""

QC_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.qc_results (
    check_id          text NOT NULL REFERENCES public.qc_checks(check_id),
    run_id            text NOT NULL,
    ran_at            timestamptz NOT NULL DEFAULT now(),
    outcome           text NOT NULL,
    tape_row_count    integer,
    fail_count        integer,
    pass_count        integer,
    sql_executed      text,
    detail            text,
    PRIMARY KEY (check_id, run_id)
);

CREATE INDEX IF NOT EXISTS qc_results_ran_at_idx
    ON public.qc_results (ran_at DESC);
"""

ASF_TAPE_COLUMNS = (
    "loan_id",
    "cutoff_date",
    "current_loan_amount",
    "current_interest_rate",
    "current_payment_amount_due",
    "remaining_term",
    "amortization_type",
    "remaining_io_months",
    "loan_age_months",
    "origination_date",
    "original_loan_amount",
    "original_appraised_property_value",
    "most_recent_property_value",
    "lien_position",
    "senior_lien_current_balance",
    "junior_lien_balance",
    "original_ltv",
    "original_cltv",
    "original_fico",
    "state",
    "postal_code",
    "property_type",
    "occupancy",
    "loan_purpose",
    "documentation_type",
    "tila_status",
    "business_purpose_flag",
    "originator_dti",
    "dscr",
    "days_delinquent",
    "liquid_cash_reserves",
    "prepayment_penalty_remaining_term",
    "arm_initial_fixed_months",
    "arm_reset_frequency_months",
    "arm_index",
    "arm_gross_margin",
    "arm_initial_cap",
    "arm_periodic_cap",
    "arm_lifetime_cap",
    "arm_lifetime_floor",
    "monthly_property_tax",
    "monthly_insurance_cost",
    "monthly_hoa_cost",
    "pitia",
    "rental_income_used_for_dscr",
    "refinance_incentive",
    "cohort",
    "has_mi",
)

# Excel Loan Tape header → asf_tape column
EXCEL_TO_ASF = {
    "LOAN_ID": "loan_id",
    "CUTOFF_DATE": "cutoff_date",
    "CURRENT_LOAN_AMOUNT": "current_loan_amount",
    "CURRENT_INTEREST_RATE": "current_interest_rate",
    "CURRENT_PAYMENT_AMOUNT_DUE": "current_payment_amount_due",
    "REMAINING_TERM": "remaining_term",
    "AMORTIZATION_TYPE": "amortization_type",
    "REMAINING_IO_MONTHS": "remaining_io_months",
    "LOAN_AGE_MONTHS": "loan_age_months",
    "ORIGINATION_DATE": "origination_date",
    "ORIGINAL_LOAN_AMOUNT": "original_loan_amount",
    "ORIGINAL_APPRAISED_PROPERTY_VALUE": "original_appraised_property_value",
    "MOST_RECENT_PROPERTY_VALUE": "most_recent_property_value",
    "LIEN_POSITION": "lien_position",
    "SENIOR_LIEN_CURRENT_BALANCE": "senior_lien_current_balance",
    "JUNIOR_LIEN_BALANCE": "junior_lien_balance",
    "ORIGINAL_LTV": "original_ltv",
    "ORIGINAL_CLTV": "original_cltv",
    "ORIGINAL_FICO": "original_fico",
    "STATE": "state",
    "POSTAL_CODE": "postal_code",
    "PROPERTY_TYPE": "property_type",
    "OCCUPANCY": "occupancy",
    "LOAN_PURPOSE": "loan_purpose",
    "DOCUMENTATION_TYPE": "documentation_type",
    "TILA_STATUS": "tila_status",
    "BUSINESS_PURPOSE_FLAG": "business_purpose_flag",
    "ORIGINATOR_DTI": "originator_dti",
    "DSCR": "dscr",
    "DAYS_DELINQUENT": "days_delinquent",
    "LIQUID_CASH_RESERVES": "liquid_cash_reserves",
    "PREPAYMENT_PENALTY_REMAINING_TERM": "prepayment_penalty_remaining_term",
    "ARM_INITIAL_FIXED_MONTHS": "arm_initial_fixed_months",
    "ARM_RESET_FREQUENCY_MONTHS": "arm_reset_frequency_months",
    "ARM_INDEX": "arm_index",
    "ARM_GROSS_MARGIN": "arm_gross_margin",
    "ARM_INITIAL_CAP": "arm_initial_cap",
    "ARM_PERIODIC_CAP": "arm_periodic_cap",
    "ARM_LIFETIME_CAP": "arm_lifetime_cap",
    "ARM_LIFETIME_FLOOR": "arm_lifetime_floor",
    "MONTHLY_PROPERTY_TAX": "monthly_property_tax",
    "MONTHLY_INSURANCE_COST": "monthly_insurance_cost",
    "MONTHLY_HOA_COST": "monthly_hoa_cost",
    "PITIA": "pitia",
    "RENTAL_INCOME_USED_FOR_DSCR": "rental_income_used_for_dscr",
    "refinance incentive": "refinance_incentive",
    "cohort": "cohort",
}
