"""Natural-language QC checks → SQL predicates against public.asf_tape.

Foundation NQM field checks plus Non-QM ASF Absolute Basis edits 1–26.
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
    source: str  # foundation | absolute_basis
    edit_number: int | None
    rule_name: str
    nl_description: str
    sql_predicate: str | None
    required_columns: tuple[str, ...]
    skip_reason: str | None = None


def _skip(edit: int, nl: str, missing: str) -> QcCheckDef:
    return QcCheckDef(
        check_id=f"abs_{edit:02d}",
        source="absolute_basis",
        edit_number=edit,
        rule_name=f"NQM-{edit}",
        nl_description=nl,
        sql_predicate=None,
        required_columns=(),
        skip_reason=f"asf_tape lacks required field(s): {missing}",
    )


# Foundational investor-tape integrity checks (valid against asf_tape columns).
FOUNDATION_CHECKS: tuple[QcCheckDef, ...] = (
    QcCheckDef(
        check_id="nqm_fico",
        source="foundation",
        edit_number=None,
        rule_name="NQM-FICO",
        nl_description="FICO In 300–850 (Not Zero Or Missing)",
        sql_predicate=(
            "original_fico IS NULL OR original_fico = 0 "
            "OR original_fico < 300 OR original_fico > 850"
        ),
        required_columns=("original_fico",),
    ),
    QcCheckDef(
        check_id="nqm_ltv",
        source="foundation",
        edit_number=None,
        rule_name="NQM-LTV",
        nl_description="LTV Present",
        sql_predicate="original_ltv IS NULL",
        required_columns=("original_ltv",),
    ),
    QcCheckDef(
        check_id="nqm_cltv",
        source="foundation",
        edit_number=None,
        rule_name="NQM-CLTV",
        nl_description="CLTV Present",
        sql_predicate="original_cltv IS NULL",
        required_columns=("original_cltv",),
    ),
    QcCheckDef(
        check_id="nqm_bal",
        source="foundation",
        edit_number=None,
        rule_name="NQM-BAL",
        nl_description="Original Balance Greater Than Zero",
        sql_predicate=(
            "original_loan_amount IS NULL OR original_loan_amount <= 0"
        ),
        required_columns=("original_loan_amount",),
    ),
)

# Absolute Basis edits 1–26 (NL from Non QM ASF Edit Checks spreadsheet).
ABSOLUTE_BASIS_CHECKS: tuple[QcCheckDef, ...] = (
    QcCheckDef(
        check_id="abs_01",
        source="absolute_basis",
        edit_number=1,
        rule_name="NQM-1",
        nl_description=(
            "Confirm Senior Loan Amount Consistent With Lien Position"
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
        rule_name="NQM-2",
        nl_description="DTI Greater Than 50%",
        sql_predicate="originator_dti IS NOT NULL AND originator_dti > 0.50",
        required_columns=("originator_dti",),
    ),
    _skip(
        3,
        "Self Employed Borrower With Full Documentation Type",
        "self_employed_flag (or equivalent)",
    ),
    _skip(4, "Paystring Check", "paystring"),
    _skip(
        5,
        "Wage Income <= 0 And Self Employed Flag Is 0",
        "wage_income, self_employed_flag",
    ),
    _skip(
        6,
        "Number Of Borrowers > 1 And Missing Co-Borrower Information",
        "number_of_borrowers, co_borrower fields",
    ),
    _skip(
        7,
        "Length Of Employment Is Blank Or 0",
        "length_of_employment",
    ),
    _skip(
        8,
        "Original Valuation Is Not A Full Appraisal",
        "original_valuation_type / appraisal_type",
    ),
    _skip(
        9,
        "Updated Credit Score Date > 360 Days (Date → Cut-Off)",
        "updated_credit_score_date",
    ),
    _skip(
        10,
        "Updated BPO Date > 24 Months From Cut Off",
        "updated_bpo_date",
    ),
    _skip(11, "Max Trade Line < 1500", "max_trade_line"),
    _skip(12, "Months BK > 0", "months_bk"),
    _skip(
        13,
        "Borrower Income Verification Level < 4 Or Blank And "
        "Co Borrower Income Verification Level < 4 Or Blank",
        "borrower_income_verification_level, "
        "co_borrower_income_verification_level",
    ),
    _skip(
        14,
        "Borrower Employment Verification Level < 3 Or Blank, "
        "Co Borrower Employment Verification Level < 3 Or Blank",
        "borrower_employment_verification_level, "
        "co_borrower_employment_verification_level",
    ),
    _skip(
        15,
        "Asset Verification Greater Than 1 But Reserves Eq 0",
        "asset_verification_level (reserves=liquid_cash_reserves present)",
    ),
    _skip(
        16,
        "Original Appraisal Value Date Is Later Than The Origination Date",
        "original_appraisal_date",
    ),
    _skip(
        17,
        "Non-Cashout Loan With Cashout > 2K",
        "cashout_amount",
    ),
    _skip(
        18,
        "First Time Home Buyer With Multiple Mortgaged Properties",
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
        rule_name="NQM-20",
        nl_description="Zip Code Is Not 5 Digits",
        sql_predicate=(
            "postal_code IS NULL OR length(regexp_replace("
            "trim(postal_code), '[^0-9]', '', 'g')) <> 5"
        ),
        required_columns=("postal_code",),
    ),
    _skip(
        21,
        "Original FICO Date Is After Origination Date",
        "original_fico_date",
    ),
    _skip(
        22,
        "Total Origination And Discount Points < 0 For Non-Exempt Loans",
        "origination_discount_points, exemption flag",
    ),
    _skip(
        23,
        "Fixed Rate — If DSCR Is Null Or 0 And Amortization Type = 1 And "
        "Qualification Method Should Be Either 1 Or 4, Flag If Other",
        "qualification_method (dscr + amortization_type present)",
    ),
    QcCheckDef(
        check_id="abs_24",
        source="absolute_basis",
        edit_number=24,
        rule_name="NQM-24",
        nl_description="Origination Date After Actual Cut-Off Date",
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
        rule_name="NQM-25",
        nl_description="Reported LTV Is Inconsistent With Calculated LTV",
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
        rule_name="NQM-26",
        nl_description=(
            "Reported Combined LTV Is Inconsistent With Calculated Combined LTV"
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

ALL_CHECKS: tuple[QcCheckDef, ...] = FOUNDATION_CHECKS + ABSOLUTE_BASIS_CHECKS
CHECKS_BY_ID: dict[str, QcCheckDef] = {c.check_id: c for c in ALL_CHECKS}


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
