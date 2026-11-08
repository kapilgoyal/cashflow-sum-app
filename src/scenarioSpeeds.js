/**
 * Cohort PSA/SDA speed schedule + curve helpers.
 * Speeds come from shared data/scenario_config.json (mirrored at ./scenario_config.json).
 */
import scenarioConfig from "./scenario_config.json";
import {
  HLTV_STRONG_RI,
  HLTV_WEAK_RI,
  LLTV_WEAK_RI,
} from "./cohortLabels";

/** PSA Down/Base/Up · SDA Low/Base/High per cohort (Scenarios wide grid). */
export const COHORT_SPEED_SCHEDULE = scenarioConfig.cohort_speed_schedule;

export const SCENARIO_CONFIG_VERSION = scenarioConfig.version;

export const WAL_KIND_LABELS = scenarioConfig.wal || {};

/** Grid axes for the 27-cell PSA×SDA cross (same as backend). */
export const GRID_AXES = scenarioConfig.grid_axes;

export function labelPsaSda(psa, sda) {
  return `PSA ${Number(psa)} / SDA ${Number(sda)}`;
}

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

/** Sanity: schedule cohorts match known labels (dev aid). */
export const EXPECTED_SCHEDULE_COHORTS = [
  HLTV_STRONG_RI,
  HLTV_WEAK_RI,
  LLTV_WEAK_RI,
];
