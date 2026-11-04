/**
 * API base for CashFlow.
 *
 * - Local Vite: leave unset → relative `/api/...` (proxied to uvicorn :8000).
 * - Combined container (Azure Container Apps): leave unset → same-origin `/api`.
 * - Split Vercel UI: set `VITE_API_BASE_URL` at build time to the always-on
 *   FastAPI host (e.g. https://cashflow-api.up.railway.app) with no trailing slash.
 */
const RAW = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");

export function apiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return RAW ? `${RAW}${p}` : p;
}
