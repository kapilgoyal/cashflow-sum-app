/**
 * Cohort PSA/SDA speed schedule + curve helpers (match app/services psa_prepay / sda_default).
 */
import {
  HLTV_STRONG_RI,
  HLTV_WEAK_RI,
  LLTV_WEAK_RI,
} from "./cohortLabels";

/** PSA Down/Base/Up · SDA Low/Base/High per cohort (Scenarios wide grid). */
export const COHORT_SPEED_SCHEDULE = [
  {
    cohort: HLTV_STRONG_RI,
    psaDown: 100,
    psaBase: 150,
    psaUp: 225,
    sdaLow: 100,
    sdaBase: 150,
    sdaHigh: 300,
  },
  {
    cohort: HLTV_WEAK_RI,
    psaDown: 50,
    psaBase: 75,
    psaUp: 100,
    sdaLow: 150,
    sdaBase: 250,
    sdaHigh: 450,
  },
  {
    cohort: LLTV_WEAK_RI,
    psaDown: 75,
    psaBase: 100,
    psaUp: 125,
    sdaLow: 25,
    sdaBase: 75,
    sdaHigh: 150,
  },
];

function uniqSorted(nums) {
  return [...new Set(nums.map(Number).filter((n) => Number.isFinite(n)))].sort(
    (a, b) => a - b
  );
}

/** All distinct PSA multiples across the schedule. */
export function distinctPsaMultiples(schedule = COHORT_SPEED_SCHEDULE) {
  return uniqSorted(
    schedule.flatMap((r) => [r.psaDown, r.psaBase, r.psaUp])
  );
}

/** All distinct SDA multiples across the schedule. */
export function distinctSdaMultiples(schedule = COHORT_SPEED_SCHEDULE) {
  return uniqSorted(
    schedule.flatMap((r) => [r.sdaLow, r.sdaBase, r.sdaHigh])
  );
}

/** Annual CPR under n% PSA (SIFMA). */
export function cprAtAge(ageMonths, psaMultiple) {
  const age = Math.max(Number(ageMonths) || 1, 1);
  const base = age <= 30 ? 0.002 * age : 0.06;
  return Math.max(0, (Number(psaMultiple) / 100) * base);
}

/** Annual CDR under n% SDA (GFMI/SIFMA). */
export function cdrAtAge(ageMonths, sdaMultiple) {
  const age = Math.max(Number(ageMonths) || 1, 1);
  let base;
  if (age <= 30) base = 0.0002 * age;
  else if (age <= 60) base = 0.006;
  else if (age <= 120) {
    base = 0.006 + (0.0003 - 0.006) * (age - 60) / 60;
  } else base = 0.0003;
  return Math.max(0, (Number(sdaMultiple) / 100) * base);
}

/** Chart rows month 1..n with psa_<m>_cpr / sda_<m>_cdr columns. */
export function buildSpeedChartRows(
  months,
  psaMultiples = distinctPsaMultiples(),
  sdaMultiples = distinctSdaMultiples()
) {
  const rows = [];
  for (let m = 1; m <= months; m += 1) {
    const row = { month: m };
    for (const p of psaMultiples) row[`psa_${p}_cpr`] = cprAtAge(m, p);
    for (const s of sdaMultiples) row[`sda_${s}_cdr`] = cdrAtAge(m, s);
    rows.push(row);
  }
  return rows;
}

const SPEED_PALETTE = [
  "#4A5F7A",
  "#6B7C93",
  "#FD9D24",
  "#1F8A44",
  "#2A9D8F",
  "#C51D46",
  "#9B59B6",
  "#E67E22",
];

export function seriesForMultiples(kind, multiples) {
  const prefix = kind === "psa" ? "psa" : "sda";
  const suffix = kind === "psa" ? "cpr" : "cdr";
  const unit = kind === "psa" ? "PSA" : "SDA";
  return multiples.map((m, i) => ({
    key: `${prefix}_${m}_${suffix}`,
    label: `${m} ${unit}`,
    color: SPEED_PALETTE[i % SPEED_PALETTE.length],
    multiple: m,
  }));
}
