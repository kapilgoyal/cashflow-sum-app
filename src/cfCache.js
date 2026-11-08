/**
 * CF-191: load cashflow caches only via API fingerprint gates.
 * Never fall back to static public/*.json — that bypasses stale rejection.
 */
import { apiUrl } from "./apiBase";

function detailMessage(payload, fallback) {
  if (payload == null) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (payload.detail && typeof payload.detail === "object") {
    return payload.detail.error || JSON.stringify(payload.detail);
  }
  if (payload.error) return String(payload.error);
  return fallback;
}

/**
 * GET a CF cache endpoint. On 404/409 returns a clear recompute Error
 * (no static JSON fallback).
 */
export async function fetchFreshCf(path, { recomputeHint } = {}) {
  const res = await fetch(apiUrl(path));
  if (res.ok) return res.json();
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const hint =
    recomputeHint ||
    "Recompute the matching POST /api/cashflows/run-*?force=true endpoint.";
  const msg = detailMessage(
    body,
    `Cashflow cache unavailable (HTTP ${res.status}). ${hint}`
  );
  const err = new Error(msg);
  err.status = res.status;
  err.body = body;
  throw err;
}

export function fetchScenarioGridCf() {
  return fetchFreshCf("/api/cashflows/scenario-grid", {
    recomputeHint:
      "POST /api/cashflows/run-scenario-grid?force=true to rebuild all 27 cells.",
  });
}

export function fetchBaseCohortCf() {
  return fetchFreshCf("/api/cashflows/base-cohort", {
    recomputeHint:
      "POST /api/cashflows/run-base-cohort?force=true before Valuation / charts.",
  });
}
