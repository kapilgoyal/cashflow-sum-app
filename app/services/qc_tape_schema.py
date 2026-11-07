"""asf_tape column catalog for Groq QC translation prompts."""

from __future__ import annotations

# Short typed notes shared with the LLM (failing-row WHERE fragments only).
TAPE_COLUMN_DOCS: tuple[tuple[str, str, str], ...] = (
    ("loan_id", "text", "Primary key"),
    ("cutoff_date", "date", "Pool cut-off"),
    ("current_loan_amount", "float", "Current UPB dollars"),
    ("current_interest_rate", "float", "Coupon as decimal (0.075 = 7.5%)"),
    ("current_payment_amount_due", "float", "Monthly payment due"),
    ("remaining_term", "int", "Months remaining"),
    ("amortization_type", "text", "Amortization code/label"),
    ("remaining_io_months", "int", "IO months left"),
    ("loan_age_months", "int", "Seasoning months"),
    ("origination_date", "date", "Origination"),
    ("original_loan_amount", "float", "Original balance dollars"),
    ("original_appraised_property_value", "float", "Appraisal dollars"),
    ("most_recent_property_value", "float", "Updated value dollars"),
    ("lien_position", "int", "1 = first lien"),
    ("senior_lien_current_balance", "float", "Senior lien UPB"),
    ("junior_lien_balance", "float", "Junior lien balance"),
    ("original_ltv", "float", "LTV decimal (0.80 = 80%)"),
    ("original_cltv", "float", "CLTV decimal"),
    ("original_fico", "int", "FICO 300–850"),
    ("state", "text", "US state code"),
    ("postal_code", "text", "ZIP; prefer 5 digits"),
    ("property_type", "text", "Property type"),
    ("occupancy", "text", "Occupancy"),
    ("loan_purpose", "text", "Purchase / refi / etc."),
    ("documentation_type", "text", "Doc type"),
    ("tila_status", "text", "TILA status"),
    ("business_purpose_flag", "text", "Business-purpose flag"),
    ("originator_dti", "float", "DTI decimal (0.45 = 45%)"),
    ("dscr", "float", "DSCR ratio (1.25 = 1.25x)"),
    ("days_delinquent", "int", "DQ days"),
    ("liquid_cash_reserves", "float", "Reserves dollars"),
    ("prepayment_penalty_remaining_term", "int", "PPP months left"),
    ("arm_initial_fixed_months", "int", "ARM initial fixed"),
    ("arm_reset_frequency_months", "int", "ARM reset freq"),
    ("arm_index", "text", "ARM index"),
    ("arm_gross_margin", "float", "ARM margin decimal"),
    ("arm_initial_cap", "float", "Initial cap decimal"),
    ("arm_periodic_cap", "float", "Periodic cap decimal"),
    ("arm_lifetime_cap", "float", "Lifetime cap decimal"),
    ("arm_lifetime_floor", "float", "Lifetime floor decimal"),
    ("monthly_property_tax", "float", "Tax dollars/mo"),
    ("monthly_insurance_cost", "float", "Insurance dollars/mo"),
    ("monthly_hoa_cost", "float", "HOA dollars/mo"),
    ("pitia", "float", "PITIA dollars/mo"),
    ("rental_income_used_for_dscr", "float", "Rental income for DSCR"),
    ("refinance_incentive", "float", "Refi incentive points"),
    ("cohort", "text", "HLTV/LLTV Strong|Moderate|Weak RI"),
    ("has_mi", "bool", "Mortgage insurance flag"),
)


def schema_prompt_block() -> str:
    lines = [
        "Table public.asf_tape — each row is one loan. Columns:",
    ]
    for name, typ, note in TAPE_COLUMN_DOCS:
        lines.append(f"- {name} ({typ}): {note}")
    lines.append(
        "Percents (LTV, CLTV, DTI, rates) are stored as decimals "
        "(80% → 0.80). FICO is an integer."
    )
    return "\n".join(lines)
