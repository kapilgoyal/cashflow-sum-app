"""Natural-language QC checks → SQL predicates against public.asf_tape.

Demo presence/range checks plus Non-QM ASF Absolute Basis edits 1–26.
Checks whose required columns are absent from asf_tape are stored as skipped.
SQL predicates identify FAILING rows (recomputed from Neon asf_tape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Absolute difference (decimal LTV/CLTV) beyond which reported ≠ calculated.
LTV_ABS_TOL = 0.005


@dataclass(frozen=True)
class QcCheckDef:
    check_id: str
    source: str  # demo | absolute_basis
    edit_number: int | None
    nl_description: str
    sql_predicate: str | None
    required_columns: tuple[str, ...]
    skip_reason: str | None = None


def _skip(edit: int, nl: str, missing: str) -> QcCheckDef:
    return QcCheckDef(
        check_id=f"abs_{edit:02d}",
        source="absolute_basis",
        edit_number=edit,
        nl_description=nl,
        sql_predicate=None,
        required_columns=(),
        skip_reason=f"asf_tape lacks required field(s): {missing}",
    )


# Demo QC: pass when condition holds; sql_predicate = failing rows.
DEMO_CHECKS: tuple[QcCheckDef, ...] = (
    QcCheckDef(
        check_id="demo_dti_present_gt_5pct",
        source="demo",
        edit_number=None,
        nl_description="DTI not missing and >5%",
        # Tape stores DTI as decimal ratio (0.05 = 5%).
        sql_predicate=(
            "originator_dti IS NULL OR originator_dti <= 0.05"
        ),
        required_columns=("originator_dti",),
    ),
    QcCheckDef(
        check_id="demo_income_present",
        source="demo",
        edit_number=None,
        nl_description="Income present",
        # Minimum Case tape has no borrower/wage income column.
        sql_predicate=None,
        required_columns=(),
        skip_reason=(
            "asf_tape lacks required field(s): borrower_income / "
            "monthly_qualifying_income"
        ),
    ),
    QcCheckDef(
        check_id="demo_fico_present_range",
        source="demo",
        edit_number=None,
        nl_description="FICO in 300–850 (not zero/missing)",
        sql_predicate=(
            "original_fico IS NULL OR original_fico = 0 "
            "OR original_fico < 300 OR original_fico > 850"
        ),
        required_columns=("original_fico",),
    ),
    QcCheckDef(
        check_id="demo_zip_five_digit",
        source="demo",
        edit_number=None,
        nl_description="Five-digit zip",
        sql_predicate=(
            "postal_code IS NULL OR length(regexp_replace("
            "trim(postal_code), '[^0-9]', '', 'g')) <> 5"
        ),
        required_columns=("postal_code",),
    ),
    QcCheckDef(
        check_id="demo_orig_balance_gt_0",
        source="demo",
        edit_number=None,
        nl_description="Original balance > 0",
        sql_predicate=(
            "original_loan_amount IS NULL OR original_loan_amount <= 0"
        ),
        required_columns=("original_loan_amount",),
    ),
    QcCheckDef(
        check_id="demo_ltv_present",
        source="demo",
        edit_number=None,
        nl_description="LTV present",
        sql_predicate="original_ltv IS NULL",
        required_columns=("original_ltv",),
    ),
    QcCheckDef(
        check_id="demo_cltv_present",
        source="demo",
        edit_number=None,
        nl_description="CLTV present",
        sql_predicate="original_cltv IS NULL",
        required_columns=("original_cltv",),
    ),
)

# Absolute Basis edits 1–26 (NL from Non QM ASF Edit Checks spreadsheet).
ABSOLUTE_BASIS_CHECKS: tuple[QcCheckDef, ...] = (
    QcCheckDef(
        check_id="abs_01",
        source="absolute_basis",
        edit_number=1,
        nl_description=(
            "Confirm senior loan amount consistent with lien position"
        ),
        sql_predicate=(
            "("
            "  lien_position = 1"
            "  AND COALESCE(senior_lien_current_balance, 0) > 0"
            ") OR ("
            "  lien_position IS DISTINCT FROM 1"
            "  AND COALESCE(senior_lien_current_balance, 0) <= 0"
            ")"
        ),
        required_columns=("lien_position", "senior_lien_current_balance"),
    ),
    QcCheckDef(
        check_id="abs_02",
        source="absolute_basis",
        edit_number=2,
        nl_description="DTI > 50%",
        sql_predicate="originator_dti IS NOT NULL AND originator_dti > 0.50",
        required_columns=("originator_dti",),
    ),
    _skip(
        3,
        "Self Employed Borrower with Full documentation type",
        "self_employed_flag (or equivalent)",
    ),
    _skip(4, "Paystring Check", "paystring"),
    _skip(
        5,
        "Wage Income <= 0 and Self Employed Flag is 0",
        "wage_income, self_employed_flag",
    ),
    _skip(
        6,
        "Number of borrowers > 1 and missing co-borrower information",
        "number_of_borrowers, co_borrower fields",
    ),
    _skip(
        7,
        "Length of employment is blank or 0",
        "length_of_employment",
    ),
    _skip(
        8,
        "Original Valuation is not a full appraisal",
        "original_valuation_type / appraisal_type",
    ),
    _skip(
        9,
        "Updated credit score date > 360 Days (date --> cut-off)",
        "updated_credit_score_date",
    ),
    _skip(
        10,
        "Updated BPO Date > 24 months from Cut Off",
        "updated_bpo_date",
    ),
    _skip(11, "max trade line < 1500", "max_trade_line"),
    _skip(12, "Months BK > 0", "months_bk"),
    _skip(
        13,
        "Borrower Income Verification Level < 4 or blank AND "
        "Co Borrower Income Verification Level < 4 or blank",
        "borrower_income_verification_level, "
        "co_borrower_income_verification_level",
    ),
    _skip(
        14,
        "Borrower Employment Verification Level < 3 or blank, "
        "Co Borrower Employment Verification Level < 3 or blank",
        "borrower_employment_verification_level, "
        "co_borrower_employment_verification_level",
    ),
    _skip(
        15,
        "Asset Verification greater than 1 but Reserves eq 0",
        "asset_verification_level (reserves=liquid_cash_reserves present)",
    ),
    _skip(
        16,
        "Original Appraisal value Date is later than the Origination Date",
        "original_appraisal_date",
    ),
    _skip(
        17,
        "Non-Cashout Loan with Cashout > 2K",
        "cashout_amount",
    ),
    _skip(
        18,
        "First Time Home Buyer with multiple mortgaged properties",
        "first_time_home_buyer, mortgaged_property_count",
    ),
    _skip(
        19,
        "Monthly Debt < Current Amount Due",
        "monthly_debt",
    ),
    QcCheckDef(
        check_id="abs_20",
        source="absolute_basis",
        edit_number=20,
        nl_description="Zip Code is not 5 digits",
        sql_predicate=(
            "postal_code IS NULL OR length(regexp_replace("
            "trim(postal_code), '[^0-9]', '', 'g')) <> 5"
        ),
        required_columns=("postal_code",),
    ),
    _skip(
        21,
        "Original FICO Date is after Origination Date",
        "original_fico_date",
    ),
    _skip(
        22,
        "Total Origination and Discount Points < 0 for non-exempt loans",
        "origination_discount_points, exemption flag",
    ),
    _skip(
        23,
        "Fixed Rate - if DSCR is null or 0 and Amortization Type = 1 and "
        "Qualification Method should be either 1 or 4, flag if other",
        "qualification_method (dscr + amortization_type present)",
    ),
    QcCheckDef(
        check_id="abs_24",
        source="absolute_basis",
        edit_number=24,
        nl_description="Origination Date after Actual Cut-off date",
        sql_predicate=(
            "origination_date IS NOT NULL AND cutoff_date IS NOT NULL "
            "AND origination_date > cutoff_date"
        ),
        required_columns=("origination_date", "cutoff_date"),
    ),
    QcCheckDef(
        check_id="abs_25",
        source="absolute_basis",
        edit_number=25,
        nl_description="Reported LTV is inconsistent with calculated LTV",
        sql_predicate=(
            "original_appraised_property_value IS NOT NULL "
            "AND original_appraised_property_value > 0 "
            "AND original_loan_amount IS NOT NULL "
            "AND original_ltv IS NOT NULL "
            "AND abs("
            "  original_ltv"
            "  - (original_loan_amount / original_appraised_property_value)"
            f") > {LTV_ABS_TOL}"
        ),
        required_columns=(
            "original_ltv",
            "original_loan_amount",
            "original_appraised_property_value",
        ),
    ),
    QcCheckDef(
        check_id="abs_26",
        source="absolute_basis",
        edit_number=26,
        nl_description=(
            "Reported Combined LTV is inconsistent with calculated Combined LTV"
        ),
        sql_predicate=(
            "original_appraised_property_value IS NOT NULL "
            "AND original_appraised_property_value > 0 "
            "AND original_loan_amount IS NOT NULL "
            "AND original_cltv IS NOT NULL "
            "AND abs("
            "  original_cltv"
            "  - ("
            "      ("
            "        original_loan_amount"
            "        + COALESCE(senior_lien_current_balance, 0)"
            "        + COALESCE(junior_lien_balance, 0)"
            "      ) / original_appraised_property_value"
            "    )"
            f") > {LTV_ABS_TOL}"
        ),
        required_columns=(
            "original_cltv",
            "original_loan_amount",
            "senior_lien_current_balance",
            "junior_lien_balance",
            "original_appraised_property_value",
        ),
    ),
)

ALL_CHECKS: tuple[QcCheckDef, ...] = DEMO_CHECKS + ABSOLUTE_BASIS_CHECKS


def checks_as_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in ALL_CHECKS:
        mode = "skipped" if c.sql_predicate is None else "active"
        rows.append(
            {
                "check_id": c.check_id,
                "source": c.source,
                "edit_number": c.edit_number,
                "nl_description": c.nl_description,
                "sql_predicate": c.sql_predicate,
                "required_columns": list(c.required_columns),
                "status_mode": mode,
                "skip_reason": c.skip_reason,
            }
        )
    return rows
