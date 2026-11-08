"""Cache keys for CF aggregates: tape hash + scenario + engine + assumptions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.assumptions import (
    assumptions_csv_path,
    default_has_mi,
    fannie_lag_relpath,
    severity_default_year_band,
    severity_grid_relpath,
)
from app.services.cashflow_engine import ENGINE_VERSION
from app.services.scenario_config import scenario_config_path


def file_sha256(path: Path | str, *, chunk: int = 1 << 20) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def text_file_sha256_normalized(path: Path | str) -> str:
    """SHA256 of UTF-8 text with newlines normalized to ``\\n`` (CRLF-safe)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def tape_hash(path: Path | str | None) -> str:
    if path is None:
        return "tape:none"
    p = Path(path)
    if not p.exists():
        return f"tape:missing:{p.name}"
    # Binary tape (xlsx) — raw bytes are fine.
    return f"tape:sha256:{file_sha256(p)}"


def assumptions_fingerprint() -> str:
    """Hash modeling assumptions that affect engine outputs (CF-176).

    Uses ENGINE_VERSION + semantic assumption values + CRLF-normalized text
    hashes so Windows-stamped JSON stays fresh inside Linux containers.
    """
    from app.services.assumptions import resolve_data_path
    from app.services.scenario_config import load_scenario_config

    parts: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "has_mi_all": default_has_mi(),
        "severity_year_band": severity_default_year_band(),
        "severity_grid_path": severity_grid_relpath(),
        "fannie_lag_path": fannie_lag_relpath(),
        "scenario_config_version": load_scenario_config().get("version"),
    }
    files = {
        "assumptions_csv": assumptions_csv_path(),
        "severity_csv": resolve_data_path(severity_grid_relpath()),
        "fannie_csv": resolve_data_path(fannie_lag_relpath()),
        "scenario_config": scenario_config_path(),
    }
    for label, p in files.items():
        if p.exists():
            parts[f"{label}_sha256"] = text_file_sha256_normalized(p)
        else:
            parts[f"{label}_sha256"] = f"missing:{p.name}"
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
    return f"assumptions:{digest}"


def scenario_fingerprint(scenario: Any) -> str:
    """Stable fingerprint for a Scenario model or mapping."""
    if hasattr(scenario, "model_dump"):
        raw = scenario.model_dump()
    elif isinstance(scenario, dict):
        raw = dict(scenario)
    else:
        raw = {"repr": repr(scenario)}
    keep = {
        k: raw.get(k)
        for k in (
            "scenario_id",
            "cohort",
            "psa_multiple",
            "sda_multiple",
            "recovery_rate",
            "recovery_lag_months",
            "recovery_period_months",
        )
        if k in raw
    }
    blob = json.dumps(keep, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f"scenario:{digest}"


def cf_cache_key(
    *,
    tape_path: Path | str | None,
    scenario: Any,
    engine_version: str = ENGINE_VERSION,
    kind: str = "loan_cf",
    months: int | None = None,
) -> str:
    """Compose an opaque cache key string for aggregate / path stores."""
    parts = [
        f"kind:{kind}",
        f"engine:{engine_version}",
        assumptions_fingerprint(),
        tape_hash(tape_path),
        scenario_fingerprint(scenario),
    ]
    if months is not None:
        parts.append(f"months:{int(months)}")
    return "|".join(parts)


def cf_cache_meta(
    *,
    tape_path: Path | str | None,
    scenario: Any,
    months: int | None = None,
    kind: str = "loan_cf",
) -> dict[str, Any]:
    return {
        "cache_key": cf_cache_key(
            tape_path=tape_path,
            scenario=scenario,
            months=months,
            kind=kind,
        ),
        "engine_version": ENGINE_VERSION,
        "assumptions_fingerprint": assumptions_fingerprint(),
        "tape_hash": tape_hash(tape_path),
        "scenario_fingerprint": scenario_fingerprint(scenario),
        "months": months,
        "kind": kind,
    }


def cache_is_fresh(
    payload: dict[str, Any] | None,
    *,
    tape_path: Path | str | None = None,
    require_tape: bool = False,
) -> bool:
    """True when cached payload matches current engine + assumptions (+ optional tape).

    Stale / missing fingerprints → False (CF-176: never serve pre-fix month1
    or grid JSON after ENGINE_VERSION or assumptions.csv change).
    """
    if not payload or not isinstance(payload, dict):
        return False
    cache = payload.get("cache") if isinstance(payload.get("cache"), dict) else {}
    engine = (
        payload.get("engine_version")
        or cache.get("engine_version")
        or (payload.get("meta") or {}).get("engine_version")
    )
    assum = (
        payload.get("assumptions_fingerprint")
        or cache.get("assumptions_fingerprint")
        or (payload.get("meta") or {}).get("assumptions_fingerprint")
    )
    if engine != ENGINE_VERSION:
        return False
    if assum != assumptions_fingerprint():
        return False
    if require_tape and tape_path is not None:
        th = (
            payload.get("tape_hash")
            or cache.get("tape_hash")
            or (payload.get("meta") or {}).get("tape_hash")
        )
        if th != tape_hash(tape_path):
            return False
    return True
