"""Read/write Neon securitization_scenarios + normalized loan CF tables."""

from __future__ import annotations

from typing import Any

from app.repositories.cashflow_schema import (
    COHORT_SCENARIO_WAL_TABLE_SQL,
    LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL,
    LOAN_CF_MONTH1_ENRICHED_VIEW_SQL,
    LOAN_CF_MONTH1_TABLE_SQL,
    LOAN_MONTH_CF_ADD_PANEL_COLS_SQL,
    LOAN_MONTH_CF_ENRICHED_VIEW_SQL,
    LOAN_MONTH_CF_TABLE_SQL,
    MONTH1_FACT_COLS,
    SCENARIO_MONTH_CF_ADD_COMPONENT_COLS_SQL,
    SCENARIO_MONTH_CF_TABLE_SQL,
)
from app.repositories.connect import connect
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.scenario_repository import CREATE_SQL as SCENARIO_SQL

PCA = {75: "Down", 100: "Base", 125: "Up"}
STA = {50: "Down", 100: "Base", 200: "Up"}

ENRICHED_SELECT_COLS = """
    scenario_id, loan_id, month, beginning_balance, interest,
    scheduled_principal, default_amt, new_default, prepay, recovery,
    ending_balance, loan_age, cpr, smm, cdr, mdr,
    used_recovery_lag_months,
    beginning_default_balance, liquidated_default, realized_loss,
    ending_default_balance, total_cash,
    cohort, psa_multiple, sda_multiple, pca_level, sta_level,
    recovery_period_months, recovery_lag_months, recovery_rate
"""


def _exec_multi(cur, sql_block: str) -> None:
    for stmt in sql_block.strip().split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)


class NeonCfRepository:
    def __init__(self, url: str | None = None) -> None:
        load_dotenv()
        self.url = url or resolve_pg_url()

    def require_url(self) -> str:
        if not self.url:
            raise RuntimeError("DATABASE_URL not set")
        return self.url

    def _connect(self):
        return connect(self.require_url(), connect_timeout=30)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCENARIO_SQL)
                cur.execute(LOAN_CF_MONTH1_TABLE_SQL)
                cur.execute(LOAN_MONTH_CF_TABLE_SQL)
                _exec_multi(cur, LOAN_MONTH_CF_ADD_PANEL_COLS_SQL)
                # DROP first: CREATE OR REPLACE cannot rename/reorder view cols.
                cur.execute(
                    "DROP VIEW IF EXISTS public.loan_month_cf_enriched CASCADE"
                )
                cur.execute(LOAN_MONTH_CF_ENRICHED_VIEW_SQL)
                _exec_multi(cur, LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL)
                cur.execute(
                    "DROP VIEW IF EXISTS public.loan_cashflows_month1_enriched CASCADE"
                )
                cur.execute(LOAN_CF_MONTH1_ENRICHED_VIEW_SQL)
                cur.execute(SCENARIO_MONTH_CF_TABLE_SQL)
                _exec_multi(cur, SCENARIO_MONTH_CF_ADD_COMPONENT_COLS_SQL)
                cur.execute(COHORT_SCENARIO_WAL_TABLE_SQL)
            conn.commit()

    def ensure_scenario_grid_schema(self) -> None:
        """Minimal DDL for 27-scenario aggregate tables (skip loan CF views)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCENARIO_SQL)
                cur.execute(SCENARIO_MONTH_CF_TABLE_SQL)
                _exec_multi(cur, SCENARIO_MONTH_CF_ADD_COMPONENT_COLS_SQL)
                cur.execute(COHORT_SCENARIO_WAL_TABLE_SQL)
            conn.commit()

    def upsert_scenarios(self, scenarios: list[Any]) -> int:
        """Upsert securitization_scenarios rows (ON CONFLICT scenario_id)."""
        self.ensure_scenario_grid_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                for s in scenarios:
                    row = s.model_dump() if hasattr(s, "model_dump") else dict(s)
                    cur.execute(
                        """
                        INSERT INTO public.securitization_scenarios (
                            scenario_id, cohort, psa_multiple, sda_multiple,
                            recovery_period_months, recovery_lag_months,
                            recovery_rate, state_varying_recovery_todo, note
                        ) VALUES (
                            %(scenario_id)s, %(cohort)s, %(psa_multiple)s,
                            %(sda_multiple)s, %(recovery_period_months)s,
                            %(recovery_lag_months)s, %(recovery_rate)s,
                            %(state_varying_recovery_todo)s, %(note)s
                        )
                        ON CONFLICT (scenario_id) DO UPDATE SET
                            cohort = EXCLUDED.cohort,
                            psa_multiple = EXCLUDED.psa_multiple,
                            sda_multiple = EXCLUDED.sda_multiple,
                            recovery_period_months = EXCLUDED.recovery_period_months,
                            recovery_lag_months = EXCLUDED.recovery_lag_months,
                            recovery_rate = EXCLUDED.recovery_rate,
                            state_varying_recovery_todo =
                                EXCLUDED.state_varying_recovery_todo,
                            note = EXCLUDED.note
                        """,
                        row,
                    )
            conn.commit()
        return len(scenarios)

    def replace_scenario_month_cf(self, rows: list[dict[str, Any]]) -> int:
        """Replace all rows in public.scenario_month_cf."""
        self.ensure_scenario_grid_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE public.scenario_month_cf")
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO public.scenario_month_cf (
                            scenario_id, month,
                            interest, scheduled_principal, prepay,
                            new_default, recovery,
                            total_cash, principal_cash, beginning_balance
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            r["scenario_id"],
                            int(r["month"]),
                            r.get("interest"),
                            r.get("scheduled_principal"),
                            r.get("prepay"),
                            r.get("new_default"),
                            r.get("recovery"),
                            r.get("total_cash"),
                            r.get("principal_cash"),
                            r.get("beginning_balance"),
                        ),
                    )
            conn.commit()
        return len(rows)

    def replace_cohort_scenario_wal(self, rows: list[dict[str, Any]]) -> int:
        """Replace all rows in public.cohort_scenario_wal."""
        self.ensure_scenario_grid_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE public.cohort_scenario_wal")
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO public.cohort_scenario_wal (
                            cohort, scenario_id, wal_years, total_cash_sum,
                            n_loans, perform_months, horizon_months
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            r["cohort"],
                            r["scenario_id"],
                            r.get("wal_years"),
                            r.get("total_cash_sum"),
                            r.get("n_loans"),
                            r.get("perform_months"),
                            r.get("horizon_months"),
                        ),
                    )
            conn.commit()
        return len(rows)

    def save_scenario_grid_cf(
        self,
        scenarios: list[Any],
        month_rows: list[dict[str, Any]],
        wal_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ensure schema, upsert scenario defs, replace aggregate CF + WAL tables."""
        self.ensure_scenario_grid_schema()
        n_scen = self.upsert_scenarios(scenarios)
        n_months = self.replace_scenario_month_cf(month_rows)
        n_wal = self.replace_cohort_scenario_wal(wal_rows)
        return {
            "scenarios_upserted": n_scen,
            "scenario_month_cf_rows": n_months,
            "cohort_scenario_wal_rows": n_wal,
        }

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
        sql = f"SELECT {ENRICHED_SELECT_COLS} FROM public.loan_cashflows_month1_enriched"
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
                    payload = dict(r)
                    if "default_amt" not in payload:
                        payload["default_amt"] = payload.get(
                            "default", payload.get("new_default")
                        )
                    for key in MONTH1_FACT_COLS:
                        payload.setdefault(key, None)
                    cur.execute(
                        f"""
                        INSERT INTO public.loan_month_cf (
                            {", ".join(MONTH1_FACT_COLS)}
                        ) VALUES (
                            %(scenario_id)s, %(loan_id)s, %(month)s,
                            %(beginning_balance)s, %(interest)s,
                            %(scheduled_principal)s, %(default_amt)s,
                            %(prepay)s, %(recovery)s, %(ending_balance)s,
                            %(loan_age)s, %(cpr)s, %(smm)s, %(cdr)s, %(mdr)s,
                            %(used_recovery_lag_months)s,
                            %(beginning_default_balance)s,
                            %(liquidated_default)s, %(realized_loss)s,
                            %(ending_default_balance)s, %(total_cash)s
                        )
                        """,
                        payload,
                    )
            conn.commit()
        return len(rows)

    def list_loan_month_cf_enriched(
        self,
        loan_id: str,
        scenario_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            f"SELECT {ENRICHED_SELECT_COLS}, loss "
            "FROM public.loan_month_cf_enriched WHERE loan_id = %s"
        )
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
