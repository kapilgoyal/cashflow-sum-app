/** Compact user-visible cohort labels. Cluster ids 0/1/2 stay the assignment keys. */

export const HLTV_STRONG_RI = "HLTV Strong RI";
export const HLTV_MODERATE_RI = "HLTV Moderate RI";
export const HLTV_WEAK_RI = "HLTV Weak RI";
export const LLTV_STRONG_RI = "LLTV Strong RI";
export const LLTV_MODERATE_RI = "LLTV Moderate RI";
export const LLTV_WEAK_RI = "LLTV Weak RI";

export const COHORT_DISPLAY_LABELS = [
  HLTV_STRONG_RI,
  HLTV_MODERATE_RI,
  HLTV_WEAK_RI,
  LLTV_STRONG_RI,
  LLTV_MODERATE_RI,
  LLTV_WEAK_RI,
];

/** k-proto scatter order matches cluster ids 0 → 1 → 2. */
export const CLUSTER_ORDER = [
  LLTV_WEAK_RI,
  HLTV_STRONG_RI,
  HLTV_WEAK_RI,
];

export const CLUSTER_COLORS = {
  [LLTV_WEAK_RI]: "#1f77b4",
  [HLTV_STRONG_RI]: "#ff7f0e",
  [HLTV_WEAK_RI]: "#2ca02c",
};

export const CLUSTER_FALLBACK_COUNTS = {
  [LLTV_WEAK_RI]: 339,
  [HLTV_STRONG_RI]: 329,
  [HLTV_WEAK_RI]: 375,
};

const ALIAS_GROUPS = [
  [
    HLTV_STRONG_RI,
    [
      "high LTV and strong refinance incentive",
      "High LTV + Strong RI",
      "High LTV Strong RI",
      "strong RI",
      "HLTV-HRI",
      "HLTV HRI",
    ],
  ],
  [
    HLTV_MODERATE_RI,
    [
      "high LTV and moderate refinance incentive",
      "High LTV + Moderate RI",
      "High LTV Moderate RI",
    ],
  ],
  [
    HLTV_WEAK_RI,
    [
      "high LTV and weak refinance incentive",
      "High LTV + Weak RI",
      "High LTV Weak RI",
      "weak RI",
      "HLTV-LRI",
      "HLTV LRI",
    ],
  ],
  [
    LLTV_STRONG_RI,
    [
      "low LTV and strong refinance incentive",
      "Low LTV + Strong RI",
      "Low LTV Strong RI",
    ],
  ],
  [
    LLTV_MODERATE_RI,
    [
      "low LTV and moderate refinance incentive",
      "Low LTV + Moderate RI",
      "Low LTV Moderate RI",
    ],
  ],
  [
    LLTV_WEAK_RI,
    [
      "low LTV and weak refinance incentive",
      "Low LTV + Weak RI",
      "Low LTV Weak RI",
      "moderate RI",
      "LLTV-LRI",
      "LLTV LRI",
    ],
  ],
];

const ALIAS_TO_CANONICAL = new Map();
const REPLACE_PAIRS = [];
for (const [canon, aliases] of ALIAS_GROUPS) {
  ALIAS_TO_CANONICAL.set(canon.toLowerCase(), canon);
  for (const alias of aliases) {
    ALIAS_TO_CANONICAL.set(alias.toLowerCase(), canon);
    if (alias !== canon) REPLACE_PAIRS.push([alias, canon]);
  }
}
REPLACE_PAIRS.sort((a, b) => b[0].length - a[0].length);

export function cohortLabel(raw) {
  if (raw == null) return "";
  const s = String(raw).trim();
  if (!s) return s;
  return ALIAS_TO_CANONICAL.get(s.toLowerCase()) || s;
}

export function relabelCohortText(text) {
  if (typeof text !== "string" || !text) return text;
  let out = text;
  for (const [alias, canon] of REPLACE_PAIRS) {
    out = out.replaceAll(alias, canon);
  }
  return out;
}

export function relabelCohortFields(row) {
  if (Array.isArray(row)) return row.map(relabelCohortFields);
  if (!row || typeof row !== "object") return row;
  const out = { ...row };
  if (out.cohort != null) out.cohort = cohortLabel(out.cohort);
  if (out.cluster != null) out.cluster = cohortLabel(out.cluster);
  if (typeof out.note === "string") out.note = relabelCohortText(out.note);
  if (out.recovery_by_cohort && typeof out.recovery_by_cohort === "object") {
    out.recovery_by_cohort = Object.fromEntries(
      Object.entries(out.recovery_by_cohort).map(([k, v]) => [cohortLabel(k), v])
    );
  }
  return out;
}

export function remappedKeyedObject(obj) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return obj || {};
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [cohortLabel(k), v])
  );
}
