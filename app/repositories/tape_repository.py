from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.models.loan import Loan

DEFAULT_TAPE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files\docs\data\Minimum_Case.xlsx"
)


class TapeRepository:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_TAPE

    def load_loan_tape(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Loan tape not found: {self.path}")
        df = pd.read_excel(self.path, sheet_name="Loan Tape")
        if "LOAN_ID" in df.columns:
            df = df.drop_duplicates(subset=["LOAN_ID"], keep="first")
        return df

    def get_loan(self, loan_id: str | None = None) -> Loan:
        df = self.load_loan_tape()
        if loan_id:
            hit = df.loc[df["LOAN_ID"].astype(str) == str(loan_id)]
            if hit.empty:
                raise KeyError(f"LOAN_ID not found: {loan_id}")
            row = hit.iloc[0]
        else:
            # Prefer fixed amortizing loan with positive payment
            fixed = df[df["AMORTIZATION_TYPE"].astype(str).str.lower().eq("fixed")]
            row = (fixed if not fixed.empty else df).iloc[0]

        return Loan(
            loan_id=str(row["LOAN_ID"]),
            current_balance=float(row["CURRENT_LOAN_AMOUNT"]),
            annual_rate=float(row["CURRENT_INTEREST_RATE"]),
            remaining_term_months=int(row["REMAINING_TERM"]),
            loan_age_months=int(row.get("LOAN_AGE_MONTHS", 0) or 0),
            monthly_payment=float(row["CURRENT_PAYMENT_AMOUNT_DUE"])
            if pd.notna(row.get("CURRENT_PAYMENT_AMOUNT_DUE"))
            else None,
            remaining_io_months=int(row.get("REMAINING_IO_MONTHS", 0) or 0),
            state=str(row["STATE"]) if pd.notna(row.get("STATE")) else None,
            cohort=str(row["cohort"]) if "cohort" in row and pd.notna(row.get("cohort")) else None,
        )
