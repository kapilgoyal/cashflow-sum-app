"""Load Minimum Case Loan Tape → public.asf_tape; persist + run QC checks.

Touches only asf_tape / qc_checks / qc_results — never loan_cashflows_month1.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg

from app.repositories.asf_qc_checks import (
    ALL_CHECKS,
    CHECKS_BY_ID,
    checks_as_rows,
)
from app.repositories.asf_tape_schema import (
    ASF_TAPE_COLUMNS,
    ASF_TAPE_HAS_MI_ALTER_SQL,
    ASF_TAPE_HAS_MI_BACKFILL_SQL,
    ASF_TAPE_HAS_MI_NOT_NULL_SQL,
    ASF_TAPE_TABLE_SQL,
    EXCEL_TO_ASF,
    QC_CHECKS_TABLE_SQL,
    QC_RESULTS_TABLE_SQL,
)
from app.services.assumptions import default_has_mi
from app.services.cohort_labels import (
    canonical_cohort_label,
    cohort_match_values,
    relabel_records,
)
from app.services.recovery import recovery_lag_months_for_state
from app.services.scenario_grid import recovery_for_cohort
from app.services.severity import resolve_loan_recovery_rate
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.tape_repository import DEFAULT_TAPE

INSERT_COLS = ", ".join(ASF_TAPE_COLUMNS)
INSERT_PLACEHOLDERS = ", ".join(f"%s" for _ in ASF_TAPE_COLUMNS)


def _pd():
    """Lazy pandas — keep Railway boot light (Neon paths don't need it)."""
    import pandas as pd

    return pd


def _to_py(v: Any) -> Any:
    pd = _pd()
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    return v


class AsfTapeRepository:
    def __init__(self, url: str | None = None) -> None:
        load_dotenv()
        self.url = url or resolve_pg_url()

    def require_url(self) -> str:
        if not self.url:
            raise RuntimeError("DATABASE_URL not set")
        return self.url

    def ensure_schema(self) -> None:
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
            conn.commit()
            with conn.cursor() as cur:
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                    conn.commit()
                except Exception:  # noqa: BLE001
                    conn.rollback()
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(QC_RESULTS_TABLE_SQL)
            conn.commit()

    def ensure_has_mi_column(self) -> bool:
        """Add + backfill has_mi DEFAULT true NOT NULL. Returns True if present."""
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
            conn.commit()
            with conn.cursor() as cur:
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                    conn.commit()
                except Exception:  # noqa: BLE001
                    # Column usable even if NOT NULL enforcement fails.
                    conn.rollback()
        return "has_mi" in self.tape_columns()

    def load_excel(self, path: Path | str | None = None) -> Any:
        pd = _pd()
        tape_path = Path(path) if path else DEFAULT_TAPE
        if not tape_path.exists():
            # Repo-bundled copy used when Agent Store path is unavailable.
            alt = Path(__file__).resolve().parents[2] / "docs" / "data" / "Minimum_Case.xlsx"
            if alt.exists():
                tape_path = alt
            else:
                raise FileNotFoundError(f"Loan tape not found: {tape_path}")
        df = pd.read_excel(tape_path, sheet_name="Loan Tape")
        if "LOAN_ID" in df.columns:
            df = df.drop_duplicates(subset=["LOAN_ID"], keep="first")
        out = pd.DataFrame()
        for excel_col, asf_col in EXCEL_TO_ASF.items():
            if excel_col in df.columns:
                out[asf_col] = df[excel_col]
            else:
                out[asf_col] = None
        # postal_code as text (preserve leading zeros when present)
        if "postal_code" in out.columns:
            out["postal_code"] = out["postal_code"].map(
                lambda x: None
                if x is None or (isinstance(x, float) and pd.isna(x))
                else str(int(x))
                if isinstance(x, (int, float)) and float(x).is_integer()
                else str(x).strip()
            )
        # has_mi from data/assumptions.csv — never from monthly_insurance_cost.
        out["has_mi"] = bool(default_has_mi())
        return out

    def replace_tape(self, df: Any) -> int:
        rows: list[tuple[Any, ...]] = []
        for _, r in df.iterrows():
            rows.append(tuple(_to_py(r.get(c)) for c in ASF_TAPE_COLUMNS))
        with psycopg.connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                except Exception:  # noqa: BLE001
                    pass
                cur.execute("TRUNCATE public.asf_tape")
                with cur.copy(
                    f"COPY public.asf_tape ({INSERT_COLS}) FROM STDIN"
                ) as copy:
                    for row in rows:
                        copy.write_row(row)
            conn.commit()
        return len(rows)

    def count_tape(self) -> int:
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.asf_tape")
                return int(cur.fetchone()[0])

    def tape_columns(self) -> set[str]:
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'asf_tape'
                    """
                )
                return {r[0] for r in cur.fetchall()}

    def upsert_check_defs(self) -> int:
        rows = checks_as_rows()
        keep_ids = tuple(r["check_id"] for r in rows)
        sql = """
            INSERT INTO public.qc_checks (
                check_id, source, edit_number, nl_description, sql_predicate,
                required_columns, status_mode, skip_reason, updated_at
            ) VALUES (
                %(check_id)s, %(source)s, %(edit_number)s, %(nl_description)s,
                %(sql_predicate)s, %(required_columns)s, %(status_mode)s,
                %(skip_reason)s, now()
            )
            ON CONFLICT (check_id) DO UPDATE SET
                source = EXCLUDED.source,
                edit_number = EXCLUDED.edit_number,
                nl_description = EXCLUDED.nl_description,
                sql_predicate = EXCLUDED.sql_predicate,
                required_columns = EXCLUDED.required_columns,
                status_mode = EXCLUDED.status_mode,
                skip_reason = EXCLUDED.skip_reason,
                updated_at = now()
        """
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                for row in rows:
                    cur.execute(sql, row)
                # Drop retired demo / obsolete check defs + their results.
                if keep_ids:
                    cur.execute(
                        "DELETE FROM public.qc_results "
                        "WHERE check_id <> ALL(%s)",
                        (list(keep_ids),),
                    )
                    cur.execute(
                        "DELETE FROM public.qc_checks "
                        "WHERE check_id <> ALL(%s)",
                        (list(keep_ids),),
                    )
            conn.commit()
        return len(rows)

    def run_qc(self, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex[:12]
        cols = self.tape_columns()
        tape_n = self.count_tape()
        results: list[dict[str, Any]] = []

        with psycopg.connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_RESULTS_TABLE_SQL)
                for check in ALL_CHECKS:
                    missing = [c for c in check.required_columns if c not in cols]
                    if check.sql_predicate is None or missing:
                        detail = check.skip_reason or (
                            f"asf_tape lacks required field(s): {', '.join(missing)}"
                            if missing
                            else "no SQL predicate"
                        )
                        row = {
                            "check_id": check.check_id,
                            "run_id": run_id,
                            "outcome": "skipped",
                            "tape_row_count": tape_n,
                            "fail_count": None,
                            "pass_count": None,
                            "sql_executed": None,
                            "detail": detail,
                        }
                    else:
                        sql = (
                            f"SELECT COUNT(*) FROM public.asf_tape "
                            f"WHERE {check.sql_predicate}"
                        )
                        cur.execute(sql)
                        fail_n = int(cur.fetchone()[0])
                        pass_n = tape_n - fail_n
                        outcome = "fail" if fail_n > 0 else "pass"
                        row = {
                            "check_id": check.check_id,
                            "run_id": run_id,
                            "outcome": outcome,
                            "tape_row_count": tape_n,
                            "fail_count": fail_n,
                            "pass_count": pass_n,
                            "sql_executed": sql,
                            "detail": None,
                        }
                    cur.execute(
                        """
                        INSERT INTO public.qc_results (
                            check_id, run_id, ran_at, outcome, tape_row_count,
                            fail_count, pass_count, sql_executed, detail
                        ) VALUES (
                            %(check_id)s, %(run_id)s, now(), %(outcome)s,
                            %(tape_row_count)s, %(fail_count)s, %(pass_count)s,
                            %(sql_executed)s, %(detail)s
                        )
                        ON CONFLICT (check_id, run_id) DO UPDATE SET
                            ran_at = now(),
                            outcome = EXCLUDED.outcome,
                            tape_row_count = EXCLUDED.tape_row_count,
                            fail_count = EXCLUDED.fail_count,
                            pass_count = EXCLUDED.pass_count,
                            sql_executed = EXCLUDED.sql_executed,
                            detail = EXCLUDED.detail
                        """,
                        row,
                    )
                    results.append(row)
            conn.commit()

        return {"run_id": run_id, "tape_row_count": tape_n, "results": results}

    def latest_results(self) -> list[dict[str, Any]]:
        """Latest run results joined with check definitions (foundation then NQM edits)."""
        sql = """
            WITH latest AS (
                SELECT run_id
                FROM public.qc_results
                ORDER BY ran_at DESC
                LIMIT 1
            )
            SELECT
                c.check_id,
                c.source,
                c.edit_number,
                c.nl_description,
                c.sql_predicate,
                c.required_columns,
                c.status_mode,
                c.skip_reason,
                r.run_id,
                r.ran_at,
                r.outcome,
                r.tape_row_count,
                r.fail_count,
                r.pass_count,
                r.sql_executed,
                r.detail
            FROM public.qc_checks c
            LEFT JOIN public.qc_results r
              ON r.check_id = c.check_id
             AND r.run_id = (SELECT run_id FROM latest)
            WHERE c.source <> 'demo'
            ORDER BY
                CASE c.source WHEN 'foundation' THEN 0 ELSE 1 END,
                c.edit_number NULLS FIRST,
                c.check_id
        """
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                out = []
                for tup in cur.fetchall():
                    row = dict(zip(cols, tup))
                    if isinstance(row.get("ran_at"), datetime):
                        row["ran_at"] = row["ran_at"].isoformat()
                    if row.get("required_columns") is not None:
                        row["required_columns"] = list(row["required_columns"])
                    cdef = CHECKS_BY_ID.get(row["check_id"])
                    row["rule_name"] = (
                        cdef.rule_name
                        if cdef
                        else (
                            f"NQM-{row['edit_number']}"
                            if row.get("edit_number") is not None
                            else row["check_id"]
                        )
                    )
                    out.append(row)
                return out

    def list_check_loans(
        self,
        check_id: str,
        *,
        failing_only: bool = True,
        limit: int = 2000,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        """Loans matching a QC check predicate (default: failing rows)."""
        check = CHECKS_BY_ID.get(check_id)
        if check is None:
            raise KeyError(f"unknown check_id: {check_id}")
        meta = {
            "check_id": check.check_id,
            "rule_name": check.rule_name,
            "nl_description": check.nl_description,
            "failing_only": failing_only,
        }
        if not check.sql_predicate:
            return [], 0, {**meta, "skipped": True, "skip_reason": check.skip_reason}

        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "original_fico",
            "original_ltv",
            "original_cltv",
            "state",
            "documentation_type",
            "property_type",
            "occupancy",
            "loan_purpose",
            "remaining_term",
            "refinance_incentive",
            "cohort",
            "has_mi",
        )
        present = self.tape_columns()
        select_cols = tuple(c for c in cols if c in present or c == "loan_id")
        # loan_id always required
        if "loan_id" not in select_cols:
            select_cols = ("loan_id",) + select_cols
        col_sql = ", ".join(select_cols)
        where = check.sql_predicate if failing_only else f"NOT ({check.sql_predicate})"
        # When failing_only=False and we want "passing", NOT (fail predicate).
        # For "all loans for rule context" callers can pass failing_only=True only.
        count_sql = f"SELECT COUNT(*) FROM public.asf_tape WHERE {where}"
        data_sql = (
            f"SELECT {col_sql} FROM public.asf_tape "
            f"WHERE {where} ORDER BY loan_id LIMIT %s"
        )
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, (limit,))
                colnames = [d.name for d in cur.description]
                loans = [dict(zip(colnames, tup)) for tup in cur.fetchall()]
        return relabel_records(loans), total, meta

    def list_loans(
        self, limit: int = 2000, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Page through asf_tape for the ASF Tape AG Grid."""
        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "remaining_term",
            "loan_age_months",
            "original_ltv",
            "original_cltv",
            "original_fico",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "documentation_type",
            "originator_dti",
            "dscr",
            "days_delinquent",
            "refinance_incentive",
            "cohort",
            "has_mi",
        )
        # Migrate before SELECT — production Neon may predate has_mi.
        has_mi_col = False
        try:
            has_mi_col = self.ensure_has_mi_column()
        except Exception:  # noqa: BLE001
            has_mi_col = "has_mi" in self.tape_columns()
        select_cols = cols if has_mi_col else tuple(c for c in cols if c != "has_mi")
        col_sql = ", ".join(select_cols)
        default_mi = bool(default_has_mi())
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.asf_tape")
                total = int(cur.fetchone()[0])
                cur.execute(
                    f"""
                    SELECT {col_sql}
                    FROM public.asf_tape
                    ORDER BY loan_id
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = []
                for tup in cur.fetchall():
                    row = dict(zip(select_cols, tup))
                    if "has_mi" not in row:
                        row["has_mi"] = default_mi
                    elif row["has_mi"] is None:
                        row["has_mi"] = default_mi
                    rows.append(row)
        return relabel_records(rows), total

    def list_loans_from_excel(
        self, path: Path | str | None = None, limit: int = 2000
    ) -> tuple[list[dict[str, Any]], int]:
        """Local fallback when Neon is unavailable."""
        df = self.load_excel(path)
        total = len(df)
        keep = [
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "remaining_term",
            "loan_age_months",
            "original_ltv",
            "original_cltv",
            "original_fico",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "documentation_type",
            "originator_dti",
            "dscr",
            "days_delinquent",
            "refinance_incentive",
            "cohort",
            "has_mi",
        ]
        for c in keep:
            if c not in df.columns:
                df[c] = None
        slim = df[keep].head(limit)
        rows = []
        for _, r in slim.iterrows():
            rows.append({c: _to_py(r.get(c)) for c in keep})
        return relabel_records(rows), total

    STRAT_DIMENSIONS = frozenset(
        {
            "documentation_type",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "cohort",
            "ltv_bucket",
            "cltv_bucket",
            "fico_band",
            "orig_year",
            "balance_band",
            "zip3",
        }
    )

    @staticmethod
    def _strat_cohort_clause(
        cohort: str | None,
    ) -> tuple[str, tuple[Any, ...], str | None]:
        cohort_filter = (cohort or "").strip()
        if cohort_filter.lower() in ("", "all", "*"):
            return "", (), None
        aliases = cohort_match_values(cohort_filter)
        display = canonical_cohort_label(cohort_filter)
        return " WHERE cohort = ANY(%s)", (aliases,), display

    @classmethod
    def _strat_bucket_expr(cls, dimension: str) -> tuple[str, str | None, bool]:
        """Return (bucket_sql, sort_sql|None, ordered)."""
        if dimension not in cls.STRAT_DIMENSIONS:
            raise ValueError(f"unsupported dimension: {dimension}")

        if dimension == "ltv_bucket":
            return (
                """
                CASE
                  WHEN original_ltv IS NULL THEN 'missing'
                  WHEN original_ltv < 0.60 THEN '<60'
                  WHEN original_ltv < 0.70 THEN '60-70'
                  WHEN original_ltv < 0.80 THEN '70-80'
                  WHEN original_ltv < 0.90 THEN '80-90'
                  ELSE '90+'
                END
                """,
                """
                CASE
                  WHEN original_ltv IS NULL THEN 99
                  WHEN original_ltv < 0.60 THEN 1
                  WHEN original_ltv < 0.70 THEN 2
                  WHEN original_ltv < 0.80 THEN 3
                  WHEN original_ltv < 0.90 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "cltv_bucket":
            return (
                """
                CASE
                  WHEN original_cltv IS NULL THEN 'missing'
                  WHEN original_cltv < 0.60 THEN '<60'
                  WHEN original_cltv < 0.70 THEN '60-70'
                  WHEN original_cltv < 0.80 THEN '70-80'
                  WHEN original_cltv < 0.90 THEN '80-90'
                  ELSE '90+'
                END
                """,
                """
                CASE
                  WHEN original_cltv IS NULL THEN 99
                  WHEN original_cltv < 0.60 THEN 1
                  WHEN original_cltv < 0.70 THEN 2
                  WHEN original_cltv < 0.80 THEN 3
                  WHEN original_cltv < 0.90 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "fico_band":
            return (
                """
                CASE
                  WHEN original_fico IS NULL THEN 'missing'
                  WHEN original_fico < 660 THEN '<660'
                  WHEN original_fico < 700 THEN '660-699'
                  WHEN original_fico < 740 THEN '700-739'
                  WHEN original_fico < 780 THEN '740-779'
                  ELSE '780+'
                END
                """,
                """
                CASE
                  WHEN original_fico IS NULL THEN 99
                  WHEN original_fico < 660 THEN 1
                  WHEN original_fico < 700 THEN 2
                  WHEN original_fico < 740 THEN 3
                  WHEN original_fico < 780 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "balance_band":
            return (
                """
                CASE
                  WHEN current_loan_amount IS NULL THEN 'missing'
                  WHEN current_loan_amount < 100000 THEN '<100k'
                  WHEN current_loan_amount < 200000 THEN '100-200k'
                  WHEN current_loan_amount < 300000 THEN '200-300k'
                  WHEN current_loan_amount < 400000 THEN '300-400k'
                  WHEN current_loan_amount < 500000 THEN '400-500k'
                  WHEN current_loan_amount < 750000 THEN '500-750k'
                  ELSE '750k+'
                END
                """,
                """
                CASE
                  WHEN current_loan_amount IS NULL THEN 99
                  WHEN current_loan_amount < 100000 THEN 1
                  WHEN current_loan_amount < 200000 THEN 2
                  WHEN current_loan_amount < 300000 THEN 3
                  WHEN current_loan_amount < 400000 THEN 4
                  WHEN current_loan_amount < 500000 THEN 5
                  WHEN current_loan_amount < 750000 THEN 6
                  ELSE 7
                END
                """,
                True,
            )
        if dimension == "orig_year":
            return (
                """
                CASE
                  WHEN origination_date IS NULL THEN 'missing'
                  ELSE EXTRACT(YEAR FROM origination_date)::int::text
                END
                """,
                """
                CASE
                  WHEN origination_date IS NULL THEN 9999
                  ELSE EXTRACT(YEAR FROM origination_date)::int
                END
                """,
                True,
            )
        if dimension == "zip3":
            # First 3 digits of postal_code (preserve leading zeros as text).
            return (
                """
                CASE
                  WHEN postal_code IS NULL
                    OR length(
                      regexp_replace(trim(postal_code), '[^0-9]', '', 'g')
                    ) < 3
                  THEN 'missing'
                  ELSE left(
                    regexp_replace(trim(postal_code), '[^0-9]', '', 'g'),
                    3
                  )
                END
                """,
                None,
                False,
            )
        # Direct column dimensions (state, documentation_type, …).
        return f"COALESCE({dimension}::text, 'missing')", None, False

    def stratification(
        self,
        dimension: str = "documentation_type",
        cohort: str | None = None,
    ) -> dict[str, Any]:
        """Bucket asf_tape by a categorical / derived dimension (not K-prototype)."""
        bucket_expr, sort_expr, ordered = self._strat_bucket_expr(dimension)
        where_sql, where_params, cohort_filter = self._strat_cohort_clause(cohort)

        wac_expr = """
            CASE
              WHEN COALESCE(SUM(current_loan_amount), 0) > 0
              THEN SUM(current_interest_rate * current_loan_amount)
                   / SUM(current_loan_amount)
              ELSE NULL
            END::float
        """

        if ordered:
            sql = f"""
                SELECT
                    {bucket_expr} AS bucket,
                    COUNT(*)::int AS loan_count,
                    COALESCE(SUM(current_loan_amount), 0)::float AS upb,
                    AVG(original_ltv)::float AS avg_ltv,
                    AVG(original_cltv)::float AS avg_cltv,
                    AVG(original_fico)::float AS avg_fico,
                    AVG(current_interest_rate)::float AS avg_rate,
                    {wac_expr} AS wac,
                    AVG(refinance_incentive)::float AS avg_refi_incentive,
                    MIN({sort_expr}) AS sort_key
                FROM public.asf_tape
                {where_sql}
                GROUP BY 1
                ORDER BY sort_key ASC NULLS LAST, bucket ASC
            """
        else:
            sql = f"""
                SELECT
                    {bucket_expr} AS bucket,
                    COUNT(*)::int AS loan_count,
                    COALESCE(SUM(current_loan_amount), 0)::float AS upb,
                    AVG(original_ltv)::float AS avg_ltv,
                    AVG(original_cltv)::float AS avg_cltv,
                    AVG(original_fico)::float AS avg_fico,
                    AVG(current_interest_rate)::float AS avg_rate,
                    {wac_expr} AS wac,
                    AVG(refinance_incentive)::float AS avg_refi_incentive
                FROM public.asf_tape
                {where_sql}
                GROUP BY 1
                ORDER BY upb DESC NULLS LAST, loan_count DESC
            """
        kpi_sql = f"""
            SELECT
                COUNT(*)::int AS tape_row_count,
                COALESCE(SUM(current_loan_amount), 0)::float AS tape_upb,
                CASE
                  WHEN COALESCE(SUM(current_loan_amount), 0) > 0
                  THEN SUM(current_interest_rate * current_loan_amount)
                       / SUM(current_loan_amount)
                  ELSE NULL
                END::float AS wac,
                CASE
                  WHEN COALESCE(SUM(current_loan_amount), 0) > 0
                  THEN SUM(remaining_term * current_loan_amount)
                       / SUM(current_loan_amount)
                  ELSE NULL
                END::float AS wam,
                CASE
                  WHEN COALESCE(
                    SUM(
                      CASE
                        WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                        THEN current_loan_amount
                        ELSE 0
                      END
                    ),
                    0
                  ) > 0
                  THEN SUM(
                    CASE
                      WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                      THEN current_interest_rate * current_loan_amount
                      ELSE 0
                    END
                  ) / SUM(
                    CASE
                      WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                      THEN current_loan_amount
                      ELSE 0
                    END
                  )
                  ELSE NULL
                END::float AS seasoned_wac,
                BOOL_OR(
                  postal_code IS NOT NULL
                  AND length(
                    regexp_replace(trim(postal_code), '[^0-9]', '', 'g')
                  ) >= 3
                ) AS has_postal_code
            FROM public.asf_tape
            {where_sql}
        """
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, where_params)
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, tup)) for tup in cur.fetchall()]
                for row in rows:
                    row.pop("sort_key", None)
                cur.execute(kpi_sql, where_params)
                kpi_cols = [d.name for d in cur.description]
                kpi = dict(zip(kpi_cols, cur.fetchone()))
        return {
            "dimension": dimension,
            "cohort": cohort_filter or "all",
            "n_buckets": len(rows),
            "tape_row_count": int(kpi["tape_row_count"] or 0),
            "tape_upb": float(kpi["tape_upb"] or 0),
            "wac": kpi.get("wac"),
            "wam": kpi.get("wam"),
            "seasoned_wac": kpi.get("seasoned_wac"),
            "has_postal_code": bool(kpi.get("has_postal_code")),
            "rows": rows,
        }

    def list_strat_loans(
        self,
        dimension: str,
        bucket: str,
        *,
        cohort: str | None = None,
        limit: int = 2000,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        """Loans matching a stratification bucket (Investor Tape–style drill)."""
        bucket_expr, _, _ = self._strat_bucket_expr(dimension)
        where_sql, where_params, cohort_filter = self._strat_cohort_clause(cohort)
        bucket_value = (bucket or "").strip()
        if not bucket_value:
            raise ValueError("bucket is required")

        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "original_fico",
            "original_ltv",
            "original_cltv",
            "state",
            "postal_code",
            "documentation_type",
            "property_type",
            "occupancy",
            "loan_purpose",
            "remaining_term",
            "refinance_incentive",
            "cohort",
            "has_mi",
            "origination_date",
        )
        present = self.tape_columns()
        select_cols = tuple(c for c in cols if c in present or c == "loan_id")
        if "loan_id" not in select_cols:
            select_cols = ("loan_id",) + select_cols
        col_sql = ", ".join(select_cols)

        if where_sql:
            filter_sql = f"{where_sql} AND ({bucket_expr}) = %s"
            params: tuple[Any, ...] = where_params + (bucket_value,)
        else:
            filter_sql = f" WHERE ({bucket_expr}) = %s"
            params = (bucket_value,)

        count_sql = f"SELECT COUNT(*) FROM public.asf_tape{filter_sql}"
        data_sql = (
            f"SELECT {col_sql} FROM public.asf_tape"
            f"{filter_sql} ORDER BY loan_id LIMIT %s"
        )
        meta = {
            "dimension": dimension,
            "bucket": bucket_value,
            "cohort": cohort_filter or "all",
        }
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, params + (limit,))
                colnames = [d.name for d in cur.description]
                loans = [dict(zip(colnames, tup)) for tup in cur.fetchall()]
                for loan in loans:
                    od = loan.get("origination_date")
                    if isinstance(od, (date, datetime)):
                        loan["origination_date"] = od.isoformat()
        return relabel_records(loans), total, meta

    def cohort_stats(self) -> list[dict[str, Any]]:
        """Per K-prototype cohort pool stats for the Cohort tab grid."""
        sql = """
            SELECT
                COALESCE(cohort, 'unlabeled') AS cohort,
                COUNT(*)::int AS loan_count,
                COALESCE(SUM(current_loan_amount), 0)::float AS upb,
                (SUM(current_interest_rate * current_loan_amount)
                    / NULLIF(SUM(current_loan_amount), 0))::float AS wac,
                (SUM(remaining_term * current_loan_amount)
                    / NULLIF(SUM(current_loan_amount), 0))::float AS wam,
                AVG(original_ltv)::float AS avg_ltv,
                AVG(original_cltv)::float AS avg_cltv,
                AVG(original_fico)::float AS avg_fico,
                AVG(current_interest_rate)::float AS avg_rate,
                AVG(refinance_incentive)::float AS avg_refi_incentive,
                AVG(remaining_term)::float AS avg_remaining_term,
                AVG(originator_dti)::float AS avg_dti
            FROM public.asf_tape
            GROUP BY 1
            ORDER BY upb DESC
        """
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, tup)) for tup in cur.fetchall()]
                cur.execute(
                    """
                    SELECT
                        COALESCE(cohort, 'unlabeled') AS cohort,
                        state,
                        original_fico,
                        original_ltv,
                        current_loan_amount,
                        has_mi
                    FROM public.asf_tape
                    """
                )
                loan_cols = [d.name for d in cur.description]
                loan_rows = [dict(zip(loan_cols, tup)) for tup in cur.fetchall()]
        weighted: dict[str, dict[str, float]] = {}
        for ln in loan_rows:
            key = canonical_cohort_label(ln.get("cohort"))
            upb = float(ln.get("current_loan_amount") or 0.0)
            try:
                cohort_rate = recovery_for_cohort(key)[0]
            except KeyError:
                cohort_rate = 0.60
            rate, _src = resolve_loan_recovery_rate(
                has_mi=ln.get("has_mi"),
                original_fico=ln.get("original_fico"),
                original_ltv=ln.get("original_ltv"),
                cohort_recovery_rate=cohort_rate,
            )
            lag = recovery_lag_months_for_state(ln.get("state"))
            slot = weighted.setdefault(key, {"upb": 0.0, "rate": 0.0, "lag": 0.0})
            slot["upb"] += upb
            slot["rate"] += rate * upb
            slot["lag"] += lag * upb
        out = relabel_records(rows)
        for row in out:
            key = canonical_cohort_label(row.get("cohort"))
            slot = weighted.get(key)
            if slot and slot["upb"] > 0:
                row["recovery"] = slot["rate"] / slot["upb"]
                row["lag"] = slot["lag"] / slot["upb"]
        return out
