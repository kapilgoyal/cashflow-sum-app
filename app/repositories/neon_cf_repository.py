"""Read/write Neon securitization_scenarios + normalized loan CF tables."""

from __future__ import annotations

from typing import Any

from app.repositories.cashflow_schema import (
    LOAN_CF_MONTH1_ENRICHED_VIEW_SQL,
    LOAN_MONTH_CF_ENRICHED_VIEW_SQL,
    LOAN_MONTH_CF_TABLE_SQL,
    MONTH1_FACT_COLS,
)
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.scenario_repository import CREATE_SQL as SCENARIO_SQL

PCA = {75: "Down", 100: "Base", 125: "Up"}
STA = {50: "Down", 100: "Base", 200: "Up"}


class NeonCfRepository:
    def __init__(self, url: str | None = None) -> None:
        load_dotenv()
        self.url = url or resolve_pg_url()

    def require_url(self) -> str:
        if not self.url:
            raise RuntimeError("DATABASE_URL not set")
        return self.url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.require_url(), connect_timeout=30)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCENARIO_SQL)
                cur.execute(LOAN_MONTH_CF_TABLE_SQL)
                cur.execute(LOAN_MONTH_CF_ENRICHED_VIEW_SQL)
                cur.execute(LOAN_CF_MONTH1_ENRICHED_VIEW_SQL)
            conn.commit()

    def list_scenarios(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scenario_id, cohort, psa_multiple, sda_multiple,
                           recovery_period_months, recovery_lag_months,
                           recovery_rate, state_varying_recovery_todo, note
                    FROM public.securitization_scenarios
                    ORDER BY scenario_id
                    """
                )
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["pca_level"] = PCA.get(r["psa_multiple"], str(r["psa_multiple"]))
            r["sta_level"] = STA.get(r["sda_multiple"], str(r["sda_multiple"]))
        return rows

    def count_scenarios(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.securitization_scenarios")
                return int(cur.fetchone()[0])

    def orphan_month1_count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM public.loan_cashflows_month1 l
                    LEFT JOIN public.securitization_scenarios s
                      ON l.scenario_id = s.scenario_id
                    WHERE s.scenario_id IS NULL
                    """
                )
                return int(cur.fetchone()[0])

    def count_month1(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1")
                return int(cur.fetchone()[0])

    def count_month1_enriched(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM public.loan_cashflows_month1_enriched"
                )
                return int(cur.fetchone()[0])

    def list_month1_enriched(
        self,
        scenario_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT scenario_id, loan_id, month, beginning_balance, interest,
                   scheduled_principal, default_amt, prepay, recovery,
                   ending_balance, loan_age, cpr, smm, cdr, mdr,
                   cohort, psa_multiple, sda_multiple, pca_level, sta_level,
                   recovery_period_months, recovery_lag_months, recovery_rate
            FROM public.loan_cashflows_month1_enriched
        """
        params: list[Any] = []
        if scenario_id:
            sql += " WHERE scenario_id = %s"
            params.append(scenario_id)
        sql += " ORDER BY scenario_id, loan_id LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]

    def distinct_month1_scenario_ids(self) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT scenario_id
                    FROM public.loan_cashflows_month1
                    ORDER BY scenario_id
                    """
                )
                return [r[0] for r in cur.fetchall()]

    def replace_loan_month_cf(
        self,
        loan_id: str,
        scenario_ids: list[str],
        rows: list[dict[str, Any]],
    ) -> int:
        """Replace multi-month rows for loan_id × scenarios (normalized cols only)."""
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                if scenario_ids:
                    cur.execute(
                        """
                        DELETE FROM public.loan_month_cf
                        WHERE loan_id = %s AND scenario_id = ANY(%s)
                        """,
                        (loan_id, scenario_ids),
                    )
                for r in rows:
                    cur.execute(
                        f"""
                        INSERT INTO public.loan_month_cf (
                            {", ".join(MONTH1_FACT_COLS)}
                        ) VALUES (
                            %(scenario_id)s, %(loan_id)s, %(month)s,
                            %(beginning_balance)s, %(interest)s,
                            %(scheduled_principal)s, %(default_amt)s,
                            %(prepay)s, %(recovery)s, %(ending_balance)s,
                            %(loan_age)s, %(cpr)s, %(smm)s, %(cdr)s, %(mdr)s
                        )
                        """,
                        r,
                    )
            conn.commit()
        return len(rows)

    def list_loan_month_cf_enriched(
        self,
        loan_id: str,
        scenario_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT scenario_id, loan_id, month, beginning_balance, interest,
                   scheduled_principal, default_amt, prepay, recovery, loss,
                   ending_balance, loan_age, cpr, smm, cdr, mdr,
                   cohort, psa_multiple, sda_multiple, pca_level, sta_level,
                   recovery_period_months, recovery_lag_months, recovery_rate
            FROM public.loan_month_cf_enriched
            WHERE loan_id = %s
        """
        params: list[Any] = [loan_id]
        if scenario_id:
            sql += " AND scenario_id = %s"
            params.append(scenario_id)
        sql += " ORDER BY scenario_id, month"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
