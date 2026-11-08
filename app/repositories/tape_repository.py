from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.loan import Loan
from app.services.cohort_labels import canonical_cohort_label
from app.services.scenario_grid import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
)


def _pd():
    import pandas as pd

    return pd

DEFAULT_TAPE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files\docs\data\Minimum_Case.xlsx"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLUSTER_TAPE = REPO_ROOT / "public" / "cluster-tape.json"

def resolve_default_tape_path() -> Path:
    """Repo-bundled Minimum Case tape, then the Windows Agent Store copy."""
    candidates = (
        REPO_ROOT / "docs" / "data" / "Minimum_Case.xlsx",
        REPO_ROOT / "data" / "Minimum_Case.xlsx",
        DEFAULT_TAPE,
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


# Display names; economics match k-proto cluster ids 0/1/2.

CLUSTER_ID_TO_COHORT = {
    0: COHORT_LOW_LTV_WEAK,
    1: COHORT_HIGH_LTV_STRONG,
    2: COHORT_HIGH_LTV_WEAK,
}


class TapeRepository:
    def __init__(
        self,
        path: Path | str | None = None,
        cluster_tape_path: Path | str | None = None,
    ) -> None:
        self.path = Path(path) if path else resolve_default_tape_path()
        self.cluster_tape_path = (
            Path(cluster_tape_path) if cluster_tape_path else DEFAULT_CLUSTER_TAPE
        )

    def load_loan_tape(self) -> Any:
        pd = _pd()
        if not self.path.exists():
            raise FileNotFoundError(f"Loan tape not found: {self.path}")
        df = pd.read_excel(self.path, sheet_name="Loan Tape")
        if "LOAN_ID" in df.columns:
            df = df.drop_duplicates(subset=["LOAN_ID"], keep="first")
        return df

    def load_cluster_map(self) -> dict[str, str]:
        """loan_id → expanded cohort display name from cluster-tape.json."""
        if not self.cluster_tape_path.exists():
            raise FileNotFoundError(
                f"Cluster tape not found: {self.cluster_tape_path}"
            )
        data = json.loads(self.cluster_tape_path.read_text(encoding="utf-8"))
        out: dict[str, str] = {}
        for row in data.get("loans") or []:
            lid = str(row.get("loanId") or "")
            if not lid:
                continue
            cohort = row.get("cluster")
            if not cohort and row.get("clusterId") is not None:
                cohort = CLUSTER_ID_TO_COHORT.get(int(row["clusterId"]))
            if cohort:
                out[lid] = canonical_cohort_label(str(cohort))
        return out

    def _row_to_loan(self, row: Any, cohort: str | None) -> Loan:
        from app.services.assumptions import default_has_mi
        from app.services.seasoning import age_at_cutoff, as_date

        pd = _pd()
        orig = as_date(row["ORIGINATION_DATE"]) if "ORIGINATION_DATE" in row.index else None
        cutoff = as_date(row["CUTOFF_DATE"]) if "CUTOFF_DATE" in row.index else None
        raw_age = row.get("LOAN_AGE_MONTHS")
        if raw_age is not None and pd.notna(raw_age):
            age_months = int(raw_age)
        else:
            # Fall back to months since origination (standard seasoning proxy).
            age_months = age_at_cutoff(
                loan_age_months=None,
                origination_date=orig,
                cutoff_date=cutoff,
            )
        fico = row.get("ORIGINAL_FICO")
        ltv = row.get("ORIGINAL_LTV")
        arm_idx = row.get("ARM_INDEX")
        arm_fixed = row.get("ARM_INITIAL_FIXED_MONTHS")
        arm_freq = row.get("ARM_RESET_FREQUENCY_MONTHS")
        return Loan(
            loan_id=str(row["LOAN_ID"]),
            current_balance=float(row["CURRENT_LOAN_AMOUNT"]),
            annual_rate=float(row["CURRENT_INTEREST_RATE"]),
            remaining_term_months=int(row["REMAINING_TERM"]),
            loan_age_months=age_months,
            monthly_payment=float(row["CURRENT_PAYMENT_AMOUNT_DUE"])
            if pd.notna(row.get("CURRENT_PAYMENT_AMOUNT_DUE"))
            else None,
            remaining_io_months=int(row.get("REMAINING_IO_MONTHS", 0) or 0),
            state=str(row["STATE"]) if pd.notna(row.get("STATE")) else None,
            cohort=cohort,
            origination_date=orig,
            cutoff_date=cutoff,
            original_fico=int(fico) if pd.notna(fico) else None,
            original_ltv=float(ltv) if pd.notna(ltv) else None,
            # From data/assumptions.csv — not from monthly_insurance_cost.
            has_mi=default_has_mi(),
            arm_index=str(arm_idx).strip()
            if arm_idx is not None and pd.notna(arm_idx) and str(arm_idx).strip()
            else None,
            arm_initial_fixed_months=int(arm_fixed)
            if arm_fixed is not None and pd.notna(arm_fixed)
            else None,
            arm_reset_frequency_months=int(arm_freq)
            if arm_freq is not None and pd.notna(arm_freq)
            else None,
        )

    def get_loan(self, loan_id: str | None = None) -> Loan:
        df = self.load_loan_tape()
        cluster_map = {}
        try:
            cluster_map = self.load_cluster_map()
        except FileNotFoundError:
            cluster_map = {}

        if loan_id:
            hit = df.loc[df["LOAN_ID"].astype(str) == str(loan_id)]
            if hit.empty:
                raise KeyError(f"LOAN_ID not found: {loan_id}")
            row = hit.iloc[0]
        else:
            fixed = df[df["AMORTIZATION_TYPE"].astype(str).str.lower().eq("fixed")]
            row = (fixed if not fixed.empty else df).iloc[0]

        pd = _pd()
        lid = str(row["LOAN_ID"])
        cohort = cluster_map.get(lid)
        if cohort is None and "cohort" in row and pd.notna(row.get("cohort")):
            cohort = str(row["cohort"])
        return self._row_to_loan(row, cohort)

    def load_all_loans(self) -> list[Loan]:
        """All tape loans tagged with k-proto cohort display names."""
        pd = _pd()
        df = self.load_loan_tape()
        cluster_map = self.load_cluster_map()
        loans: list[Loan] = []
        missing = 0
        for _, row in df.iterrows():
            lid = str(row["LOAN_ID"])
            cohort = cluster_map.get(lid)
            if not cohort:
                missing += 1
                continue
            bal = row.get("CURRENT_LOAN_AMOUNT")
            if pd.isna(bal) or float(bal) <= 0:
                continue
            loans.append(self._row_to_loan(row, cohort))
        if missing:
            # Soft note via attribute for callers/logs
            setattr(self, "last_missing_cluster", missing)
        return loans
