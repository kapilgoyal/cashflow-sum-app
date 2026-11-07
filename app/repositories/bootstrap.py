"""Create schema and load the sample tape when the database is empty."""

from __future__ import annotations

import logging
from typing import Any

from app.repositories.asf_tape_repository import AsfTapeRepository
from app.repositories.connect import (
    dialect_name,
    ensure_sqlite_parent,
    is_postgres_url,
    provider_hint,
    resolve_database_url,
    sqlite_path_from_url,
)
from app.repositories.env_load import REPO_ROOT, load_dotenv
from app.repositories.neon_cf_repository import NeonCfRepository
from app.repositories.scenario_repository import ScenarioRepository

_log = logging.getLogger("uvicorn.error")
SCENARIO_CSV = REPO_ROOT / "data" / "securitization_scenarios.csv"


def bootstrap_database() -> dict[str, Any]:
    """Idempotent: schema always; tape + scenarios only when tables are empty."""
    load_dotenv()
    url = resolve_database_url()
    ensure_sqlite_parent(url)
    status: dict[str, Any] = {
        "ok": True,
        "dialect": dialect_name(url),
        "provider": provider_hint(url),
        "postgres": is_postgres_url(url),
        "notes": [],
    }
    if not is_postgres_url(url):
        status["sqlite_path"] = str(sqlite_path_from_url(url))

    try:
        tape = AsfTapeRepository(url)
        tape.ensure_schema()
        n_tape = tape.count_tape()
        if n_tape == 0:
            df = tape.load_excel()
            n_tape = tape.replace_tape(df)
            tape.upsert_check_defs()
            run = tape.run_qc()
            status["notes"].append(
                f"loaded {n_tape} asf_tape rows; qc run_id={run.get('run_id')}"
            )
        else:
            tape.upsert_check_defs()
            status["notes"].append(f"asf_tape already has {n_tape} rows")
        status["tape_rows"] = n_tape

        cf = NeonCfRepository(url)
        cf.ensure_schema()

        n_scen = cf.count_scenarios()
        if n_scen == 0:
            msg = ScenarioRepository(SCENARIO_CSV).try_seed_neon()
            status["notes"].append(msg)
            n_scen = cf.count_scenarios()
        else:
            status["notes"].append(f"securitization_scenarios already has {n_scen} rows")
        status["scenario_rows"] = n_scen
    except Exception as exc:  # noqa: BLE001
        status["ok"] = False
        status["error"] = f"{type(exc).__name__}: {exc}"
        _log.exception("database bootstrap failed")
    return status


def bootstrap_status_log_line(status: dict[str, Any]) -> str:
    path = status.get("sqlite_path")
    loc = path or status.get("provider")
    if status.get("ok"):
        return (
            f"database bootstrap {status.get('dialect')} ({loc}): "
            + "; ".join(status.get("notes") or [])
        )
    return f"database bootstrap failed ({loc}): {status.get('error')}"
