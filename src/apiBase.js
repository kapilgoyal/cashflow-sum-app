/**
 * API base for CashFlow.
 *
 * - Local Vite: leave unset → relative `/api/...` (proxied to uvicorn :8000).
 * - Combined container (Azure Container Apps): leave unset → same-origin `/api`.
 * - Optional override: set `VITE_API_BASE_URL` at build time (no trailing slash)
 *   only when the UI and API are on different origins.
 */
const RAW = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");

export function apiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return RAW ? `${RAW}${p}` : p;
}
