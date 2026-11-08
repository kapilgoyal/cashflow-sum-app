"""Download and cache FRED constant-maturity Treasury yields for valuation."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.repositories.env_load import REPO_ROOT, load_dotenv

_log = logging.getLogger("uvicorn.error")

DATA_DIR = REPO_ROOT / "data"
CACHE_PATH = DATA_DIR / "fred_treasury_curve.json"

# Constant-maturity Treasury series (par yields, percent).
# 40Y is not published on FRED CMT — we extrapolate from 20Y→30Y for the chart.
FRED_SERIES: list[tuple[str, float]] = [
    ("DGS1MO", 1 / 12),
    ("DGS3MO", 0.25),
    ("DGS6MO", 0.5),
    ("DGS1", 1.0),
    ("DGS2", 2.0),
    ("DGS3", 3.0),
    ("DGS5", 5.0),
    ("DGS7", 7.0),
    ("DGS10", 10.0),
    ("DGS20", 20.0),
    ("DGS30", 30.0),
]

CACHE_MAX_AGE_HOURS = 24


def _csv_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def _fetch_latest_yield(series_id: str) -> tuple[date, float] | None:
    """Return (obs_date, yield_decimal) for the latest non-missing observation."""
    req = urllib.request.Request(
        _csv_url(series_id),
        headers={"User-Agent": "cashflow-sum-app/valuation"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    last: tuple[date, float] | None = None
    for row in reader:
        raw = (row.get(series_id) or row.get("VALUE") or "").strip()
        if not raw or raw == ".":
            continue
        try:
            y = float(raw) / 100.0
            d = datetime.strptime(row["DATE"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        last = (d, y)
    return last


def _load_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.is_file():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_is_fresh(payload: dict[str, Any]) -> bool:
    fetched = payload.get("fetched_at")
    if not fetched:
        return False
    try:
        ts = datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return age_h <= CACHE_MAX_AGE_HOURS and bool(payload.get("points"))


def download_treasury_curve(*, force: bool = False) -> dict[str, Any]:
    """Fetch FRED CMT curve, cache under data/, extrapolate a 40Y point."""
    load_dotenv()
    cached = _load_cache()
    # Prefer local cache unless caller forces a refresh (keeps Valuation snappy offline).
    if cached and cached.get("points") and not force:
        stale = not _cache_is_fresh(cached)
        return {**cached, "cached": True, "stale": stale}

    points: list[dict[str, Any]] = []
    as_of: date | None = None
    errors: list[str] = []

    def _one(series_id: str, tenor_y: float) -> tuple[str, float, Any]:
        try:
            hit = _fetch_latest_yield(series_id)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return series_id, tenor_y, exc
        return series_id, tenor_y, hit

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [
            pool.submit(_one, series_id, tenor_y)
            for series_id, tenor_y in FRED_SERIES
        ]
        for fut in as_completed(futs):
            series_id, tenor_y, result = fut.result()
            if isinstance(result, Exception):
                errors.append(f"{series_id}: {result}")
                continue
            if not result:
                errors.append(f"{series_id}: no observation")
                continue
            obs_d, yld = result
            as_of = obs_d if as_of is None else max(as_of, obs_d)
            points.append(
                {
                    "series_id": series_id,
                    "tenor_years": tenor_y,
                    "yield": round(yld, 8),
                    "yield_pct": round(yld * 100.0, 4),
                    "as_of": obs_d.isoformat(),
                    "extrapolated": False,
                }
            )

    if not points:
        if cached and cached.get("points"):
            return {
                **cached,
                "cached": True,
                "stale": True,
                "error": "; ".join(errors) or "FRED download failed",
            }
        raise RuntimeError(
            "FRED Treasury download failed: " + ("; ".join(errors) or "unknown")
        )

    points.sort(key=lambda p: float(p["tenor_years"]))
    # Synthetic 40Y for the long-end chart (flat extrapolation slope 20→30).
    p20 = next((p for p in points if abs(float(p["tenor_years"]) - 20) < 1e-9), None)
    p30 = next((p for p in points if abs(float(p["tenor_years"]) - 30) < 1e-9), None)
    if p30:
        y40 = float(p30["yield"])
        if p20:
            y40 = float(p30["yield"]) + (float(p30["yield"]) - float(p20["yield"]))
        points.append(
            {
                "series_id": "DGS40_EXTRAP",
                "tenor_years": 40.0,
                "yield": round(y40, 8),
                "yield_pct": round(y40 * 100.0, 4),
                "as_of": (as_of or date.today()).isoformat(),
                "extrapolated": True,
            }
        )

    payload: dict[str, Any] = {
        "source": "FRED CMT (fredgraph.csv)",
        "as_of": (as_of or date.today()).isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fred_api_key_configured": bool(
            (os.environ.get("FRED_API_KEY") or "").strip()
        ),
        "points": points,
        "errors": errors,
        "note": "40Y is extrapolated from the 20Y–30Y slope (not a FRED series).",
        "cached": False,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log.info("FRED Treasury curve cached → %s (%s pts)", CACHE_PATH.name, len(points))
    return payload


def get_treasury_curve(*, force: bool = False) -> dict[str, Any]:
    return download_treasury_curve(force=force)
