"""Authoritative scenario / speed / recovery config (shared with UI JSON).

Source of truth: ``data/scenario_config.json``. Backend modules and the
frontend ``src/scenario_config.json`` mirror must stay identical (see tests).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.cohort_labels import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    canonical_cohort_label,
)

_CONFIG_NAME = "scenario_config.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def scenario_config_path() -> Path:
    return _repo_root() / "data" / _CONFIG_NAME


def frontend_scenario_config_path() -> Path:
    return _repo_root() / "src" / _CONFIG_NAME


@lru_cache(maxsize=1)
def load_scenario_config() -> dict[str, Any]:
    path = scenario_config_path()
    if not path.exists():
        raise FileNotFoundError(f"scenario config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def reload_scenario_config() -> dict[str, Any]:
    load_scenario_config.cache_clear()
    return load_scenario_config()


def cohort_speed_schedule() -> list[dict[str, Any]]:
    return list(load_scenario_config()["cohort_speed_schedule"])


def base_speeds() -> dict[str, tuple[int, int]]:
    """cohort → (psaBase, sdaBase) for Base-case WAL / cash charts."""
    out: dict[str, tuple[int, int]] = {}
    for row in cohort_speed_schedule():
        key = canonical_cohort_label(row["cohort"])
        out[key] = (int(row["psaBase"]), int(row["sdaBase"]))
    return out


def grid_psa_multiples() -> tuple[int, ...]:
    return tuple(int(x) for x in load_scenario_config()["grid_axes"]["psa_multiples"])


def grid_sda_multiples() -> tuple[int, ...]:
    return tuple(int(x) for x in load_scenario_config()["grid_axes"]["sda_multiples"])


def psa_level_name(psa: int) -> str:
    names = load_scenario_config()["grid_axes"]["psa_level_names"]
    return str(names.get(str(int(psa)), str(psa)))


def sda_level_name(sda: int) -> str:
    names = load_scenario_config()["grid_axes"]["sda_level_names"]
    return str(names.get(str(int(sda)), str(sda)))


def cohort_recovery_map() -> dict[str, tuple[float, int, int]]:
    raw = load_scenario_config()["cohort_recovery"]
    out: dict[str, tuple[float, int, int]] = {}
    for cohort, vals in raw.items():
        key = canonical_cohort_label(cohort)
        out[key] = (
            float(vals["rate"]),
            int(vals["period_months"]),
            int(vals["lag_months"]),
        )
    return out


def label_psa_sda(psa: int, sda: int) -> str:
    return f"PSA {int(psa)} / SDA {int(sda)}"


def wal_kind_labels() -> dict[str, str]:
    return dict(load_scenario_config().get("wal") or {})


def mi_credit_recovery_notes() -> dict[str, Any]:
    return dict(load_scenario_config().get("mi_credit_recovery") or {})


# Stable cohort order for grid blocks (matches historical S01–S27).
COHORT_GRID_ORDER = (
    COHORT_LOW_LTV_WEAK,
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
)
