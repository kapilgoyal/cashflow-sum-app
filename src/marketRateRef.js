/**
 * Refinance-incentive benchmark baked into the Investor Tape.
 * RI (pp) = note_rate(%) − this rate. See docs/refinance-incentive-benchmark-lag.md
 * and scripts/export_cluster_tape.py (6.86 constant).
 */
export const MARKET_RATE_REF = {
  /** Decimal (0.0686 = 6.86%). */
  rate: 0.0686,
  /** Short KPI label. */
  label: "30Y PMMS",
  /** Survey / publisher. */
  source: "Freddie Mac PMMS",
  /** Display as-of (September 2026 monthly average). */
  asOf: "Sep 2026",
  /** ISO-ish stamp for tooling. */
  asOfIso: "2026-09",
  title:
    "Mortgage Ref Rate · Freddie Mac Primary Mortgage Market Survey 30-Year · As Of Sep 2026 (used for refinance incentive — not pool WAC)",
  /** One-line UI caption under Strats KPIs. */
  caption:
    "Mortgage Ref Rate: Freddie Mac PMMS 30Y · As Of Sep 2026",
};
