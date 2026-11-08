/**
 * Loan-Level Collateral Analysis — 10-section research dashboard.
 * Filters by existing k-proto cohorts only; does not touch CF / waterfall / Cohort tab.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiUrl } from "./apiBase";
import {
  DataGrid,
  FONT,
  StatusBanner,
  fmtLtv,
  fmtNum,
  fmtPct,
  moneyCol,
  intCol,
  ltvCol,
} from "./cashflowGrid";
import { StateChoropleth } from "./UsChoropleth";

const BAR = "#C8C8C8";
const AMBER = "#FD9D24";
const MUTED = "#808080";
const TEXT = "#FCFCFC";
const GRID = "#323232";
const EMPTY = "#121212";
const NAVY = BAR; // bar fill alias for shared chart helpers

const FICO_ORDER = ["<660", "660-699", "700-739", "740-779", "780+", "missing"];
const LTV_ORDER = ["<60", "60-70", "70-80", "80-90", "90+", "missing"];

function fmtUpbShort(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

function InfoIcon({ title, refs }) {
  const tip = [title, ...(refs || [])].filter(Boolean).join("\n• ");
  return (
    <button
      type="button"
      className="collat-info"
      title={tip}
      aria-label={`${title} Research Notes`}
    >
      i
    </button>
  );
}

function Observation({ text }) {
  if (!text) return null;
  return <p className="collat-observation">{text}</p>;
}

function SectionHead({ title, refsKey, sectionRefs, hint }) {
  const refs = sectionRefs?.[refsKey];
  return (
    <div className="collat-section-head">
      <h3 className="collat-section-title">
        {title}
        {refs ? <InfoIcon title={refs.title || title} refs={refs.refs} /> : null}
      </h3>
      {hint ? <span className="collat-section-hint">{hint}</span> : null}
    </div>
  );
}

function toggleInList(list, value) {
  const cur = list || [];
  return cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value];
}

function emptyFilters() {
  return {
    cohorts: [],
    ficoBands: [],
    ltvBands: [],
    states: [],
    documentationTypes: [],
    occupancies: [],
    purposes: [],
    propertyTypes: [],
    dtiBands: [],
    dscrBands: [],
    ageBands: [],
    couponBands: [],
    riBands: [],
    riskOnly: false,
  };
}

function applyFilters(loans, filters, ltvMode) {
  const ltvKey = ltvMode === "current" ? "ltv_band_current" : "ltv_band_original";
  return (loans || []).filter((loan) => {
    if (filters.cohorts.length && !filters.cohorts.includes(loan.cohort)) return false;
    if (filters.ficoBands.length && !filters.ficoBands.includes(loan.fico_band))
      return false;
    if (filters.ltvBands.length && !filters.ltvBands.includes(loan[ltvKey]))
      return false;
    if (filters.states.length && !filters.states.includes(loan.state)) return false;
    if (
      filters.documentationTypes.length &&
      !filters.documentationTypes.includes(loan.documentation_type)
    )
      return false;
    if (filters.occupancies.length && !filters.occupancies.includes(loan.occupancy))
      return false;
    if (filters.purposes.length && !filters.purposes.includes(loan.loan_purpose))
      return false;
    if (
      filters.propertyTypes.length &&
      !filters.propertyTypes.includes(loan.property_type)
    )
      return false;
    if (filters.dtiBands.length && !filters.dtiBands.includes(loan.dti_band))
      return false;
    if (filters.dscrBands.length && !filters.dscrBands.includes(loan.dscr_band))
      return false;
    if (filters.ageBands.length && !filters.ageBands.includes(loan.age_band))
      return false;
    if (filters.couponBands.length) {
      const r = Number(loan.current_interest_rate);
      let band = "missing";
      if (Number.isFinite(r)) {
        if (r < 0.06) band = "<6%";
        else if (r < 0.07) band = "6-7%";
        else if (r < 0.08) band = "7-8%";
        else if (r < 0.09) band = "8-9%";
        else band = "9%+";
      }
      if (!filters.couponBands.includes(band)) return false;
    }
    if (filters.riBands.length) {
      const r = Number(loan.refinance_incentive);
      let band = "missing";
      if (Number.isFinite(r)) {
        if (r < 0) band = "<0";
        else if (r < 1) band = "0-1";
        else if (r < 2) band = "1-2";
        else band = "2+";
      }
      if (!filters.riBands.includes(band)) return false;
    }
    if (filters.riskOnly && !(loan.risk_flags || []).length) return false;
    return true;
  });
}

function upbWeightedMean(loans, field) {
  let num = 0;
  let den = 0;
  for (const loan of loans) {
    const w = Number(loan.current_loan_amount);
    const v = Number(loan[field]);
    if (!Number.isFinite(w) || w <= 0 || !Number.isFinite(v)) continue;
    num += v * w;
    den += w;
  }
  return den > 0 ? num / den : null;
}

function aggregate(loans, field, order, { hideMissing = false } = {}) {
  const map = new Map();
  for (const loan of loans) {
    const raw = loan[field];
    const key = raw == null || raw === "" ? "missing" : String(raw);
    if (hideMissing && key === "missing") continue;
    const slot = map.get(key) || { bucket: key, loan_count: 0, upb: 0 };
    slot.loan_count += 1;
    slot.upb += Number(loan.current_loan_amount) || 0;
    map.set(key, slot);
  }
  let rows = [...map.values()];
  if (order) {
    const rank = Object.fromEntries(order.map((b, i) => [b, i]));
    rows.sort((a, b) => (rank[a.bucket] ?? 999) - (rank[b.bucket] ?? 999));
  } else {
    rows.sort((a, b) => b.upb - a.upb || a.bucket.localeCompare(b.bucket));
  }
  return rows;
}

function buildHeatmap(loans, ltvMode) {
  const ltvField = ltvMode === "current" ? "current_ltv" : "original_ltv";
  const cells = new Map();
  for (const loan of loans) {
    const fico = loan.fico_band || "missing";
    let ltvBand = "missing";
    const v = Number(loan[ltvField]);
    if (Number.isFinite(v)) {
      if (v < 0.6) ltvBand = "<60";
      else if (v < 0.7) ltvBand = "60-70";
      else if (v < 0.8) ltvBand = "70-80";
      else if (v < 0.9) ltvBand = "80-90";
      else ltvBand = "90+";
    }
    const key = `${fico}|${ltvBand}`;
    const slot = cells.get(key) || {
      fico_band: fico,
      ltv_band: ltvBand,
      loan_count: 0,
      upb: 0,
    };
    slot.loan_count += 1;
    slot.upb += Number(loan.current_loan_amount) || 0;
    cells.set(key, slot);
  }
  return [...cells.values()];
}

function liveObservations(loans, kpis) {
  const n = kpis.loan_count;
  if (!n) {
    const empty = "No Loans In The Current Filter.";
    return {
      fico: empty,
      ltv: empty,
      heatmap: empty,
      dti_dscr: empty,
      documentation: empty,
      mix: empty,
      coupon: empty,
      geo: empty,
      explorer: empty,
    };
  }
  const ficoRows = aggregate(loans, "fico_band"); // UPB-desc for largest-band note
  const topFico = ficoRows[0];
  const ficoShare = topFico && kpis.upb ? (topFico.upb / kpis.upb) * 100 : 0;
  const ficoObs =
    kpis.wa_fico != null
      ? `WA FICO ${kpis.wa_fico.toFixed(0)} On ${n.toLocaleString()} Loans; Largest Band ${topFico?.bucket || "—"} Holds ${ficoShare.toFixed(0)}% Of UPB`
      : `${n.toLocaleString()} Loans; FICO Coverage Incomplete`;

  const ltvRows = aggregate(loans, "ltv_band_original");
  const highUpb = ltvRows
    .filter((r) => r.bucket === "80-90" || r.bucket === "90+")
    .reduce((s, r) => s + r.upb, 0);
  const highShare = kpis.upb ? (highUpb / kpis.upb) * 100 : 0;
  const ltvObs =
    kpis.wa_ltv != null
      ? `WA Original LTV ${fmtLtv(kpis.wa_ltv)}; ≥80% LTV Is ${highShare.toFixed(0)}% Of UPB`
      : `≥80% Original LTV Is ${highShare.toFixed(0)}% Of UPB`;

  const heat = buildHeatmap(loans, "original").sort((a, b) => b.upb - a.upb);
  const heatObs = heat[0]
    ? `Largest Cell: FICO ${heat[0].fico_band} × LTV ${heat[0].ltv_band} (${heat[0].loan_count.toLocaleString()} Loans)`
    : "No FICO × LTV Cells";

  const dtiCov = loans.filter((l) => l.originator_dti != null).length / n;
  const dscrCov = loans.filter((l) => l.dscr != null).length / n;
  const dtiObs =
    kpis.wa_dti != null
      ? `DTI On ${(dtiCov * 100).toFixed(0)}% Of Loans (WA ${(kpis.wa_dti * 100).toFixed(1)}% When Present); DSCR On ${(dscrCov * 100).toFixed(0)}%`
      : `DTI Coverage ${(dtiCov * 100).toFixed(0)}%; DSCR Coverage ${(dscrCov * 100).toFixed(0)}%`;

  const docs = aggregate(loans, "documentation_type");
  const docObs = docs[0]
    ? `${docs[0].bucket} Leads At ${((docs[0].upb / kpis.upb) * 100).toFixed(0)}% Of UPB (${docs.length} Types)`
    : "No Documentation Mix";

  const occ = aggregate(loans, "occupancy");
  const purpose = aggregate(loans, "loan_purpose");
  const mixObs = `Top Occupancy ${occ[0]?.bucket || "—"}; Top Purpose ${purpose[0]?.bucket || "—"}`;

  const couponObs =
    kpis.wac != null && kpis.wa_ri != null && kpis.wa_age != null
      ? `WAC ${(kpis.wac * 100).toFixed(2)}%; WA RI ${kpis.wa_ri.toFixed(2)}; WA Age ${kpis.wa_age.toFixed(1)} Mo`
      : "Coupon / RI / Age Incomplete For Weighted Averages";

  const states = aggregate(loans, "state");
  const top10 = states.slice(0, 10).reduce((s, r) => s + r.upb, 0);
  const geoObs = states[0]
    ? `Top State ${states[0].bucket} (${states[0].loan_count.toLocaleString()} Loans); Top 10 States = ${((top10 / kpis.upb) * 100).toFixed(0)}% Of UPB`
    : "No State Concentration";

  const flagged = loans.filter((l) => (l.risk_flags || []).length).length;
  const explorerObs = `${flagged.toLocaleString()} Of ${n.toLocaleString()} Loans Carry ≥1 Diligence Flag`;

  return {
    fico: ficoObs,
    ltv: ltvObs,
    heatmap: heatObs,
    dti_dscr: dtiObs,
    documentation: docObs,
    mix: mixObs,
    coupon: couponObs,
    geo: geoObs,
    explorer: explorerObs,
  };
}

function DistBar({
  rows,
  selected,
  onSelect,
  metric = "upb",
  horizontal = false,
}) {
  const data = rows || [];
  const valueKey = metric;
  if (!data.length) return <p className="muted collat-empty">No Buckets</p>;
  const Chart = (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 8, right: 8, left: horizontal ? 8 : 0, bottom: 4 }}
      >
        <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
        {horizontal ? (
          <>
            <XAxis
              type="number"
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
              tickFormatter={(v) =>
                metric === "loan_count" ? Number(v).toLocaleString() : fmtUpbShort(v)
              }
            />
            <YAxis
              type="category"
              dataKey="bucket"
              width={110}
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
            />
          </>
        ) : (
          <>
            <XAxis
              dataKey="bucket"
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
            />
            <YAxis
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
              tickFormatter={(v) =>
                metric === "loan_count" ? Number(v).toLocaleString() : fmtUpbShort(v)
              }
            />
          </>
        )}
        <Tooltip
          formatter={(v) =>
            metric === "loan_count" ? Number(v).toLocaleString() : fmtUpbShort(v)
          }
          labelStyle={{ color: TEXT }}
        />
        <Bar
          dataKey={valueKey}
          cursor="pointer"
          onClick={(d) => d?.bucket != null && onSelect?.(d.bucket)}
        >
          {data.map((row) => (
            <Cell
              key={row.bucket}
              fill={selected?.includes(row.bucket) ? AMBER : NAVY}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
  return (
    <div className="collat-chart-wrap">
      <div className="collat-chart">{Chart}</div>
    </div>
  );
}

/** UPB bars + WAC line — click age band to cross-filter. */
function AgeWacChart({ rows, selected, onSelect }) {
  const data = rows || [];
  if (!data.length) return <p className="muted collat-empty">No Buckets</p>;
  return (
    <div className="collat-chart-wrap">
      <div className="collat-chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
          >
            <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
            <XAxis
              dataKey="bucket"
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
            />
            <YAxis
              yAxisId="upb"
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
              tickFormatter={(v) => fmtUpbShort(v)}
            />
            <YAxis
              yAxisId="wac"
              orientation="right"
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
              tickFormatter={(v) => `${(Number(v) * 100).toFixed(1)}%`}
            />
            <Tooltip
              formatter={(v, name) =>
                name === "wac"
                  ? `${(Number(v) * 100).toFixed(2)}%`
                  : fmtUpbShort(v)
              }
              labelStyle={{ color: TEXT }}
            />
            <Bar
              yAxisId="upb"
              dataKey="upb"
              name="UPB"
              cursor="pointer"
              onClick={(d) => d?.bucket != null && onSelect?.(d.bucket)}
            >
              {data.map((row) => (
                <Cell
                  key={row.bucket}
                  fill={selected?.includes(row.bucket) ? AMBER : NAVY}
                />
              ))}
            </Bar>
            <Line
              yAxisId="wac"
              type="monotone"
              dataKey="wac"
              name="WAC"
              stroke={AMBER}
              strokeWidth={2}
              dot={{ r: 3, fill: AMBER }}
              activeDot={{
                r: 5,
                onClick: (_e, payload) => {
                  const b = payload?.payload?.bucket;
                  if (b != null) onSelect?.(b);
                },
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Heatmap({ cells, onSelectCell, onSelectFico, onSelectLtv, selectedFico, selectedLtv }) {
  const max = Math.max(1, ...cells.map((c) => c.upb || 0));
  const ficoLabels = FICO_ORDER.filter((f) => f !== "missing");
  const ltvLabels = LTV_ORDER.filter((l) => l !== "missing");
  const grid = ficoLabels.map((fico) =>
    ltvLabels.map((ltv) => {
      const cell = cells.find((c) => c.fico_band === fico && c.ltv_band === ltv);
      return { fico, ltv, ...(cell || { upb: 0, loan_count: 0 }) };
    })
  );
  return (
    <div className="collat-heatmap" role="img" aria-label="FICO By LTV Heatmap">
      <div className="collat-heatmap-corner">FICO \ LTV</div>
      {ltvLabels.map((ltv) => (
        <button
          key={`h-${ltv}`}
          type="button"
          className={`collat-heatmap-axis${selectedLtv?.includes(ltv) ? " is-active" : ""}`}
          onClick={() => onSelectLtv?.(ltv)}
        >
          {ltv}
        </button>
      ))}
      {grid.map((row, i) => (
        <div key={ficoLabels[i]} className="collat-heatmap-row">
          <button
            type="button"
            className={`collat-heatmap-axis collat-heatmap-y${
              selectedFico?.includes(ficoLabels[i]) ? " is-active" : ""
            }`}
            onClick={() => onSelectFico?.(ficoLabels[i])}
          >
            {ficoLabels[i]}
          </button>
          {row.map((cell) => {
            const t = cell.upb / max;
            const bg =
              cell.upb > 0
                ? `rgba(253, 157, 36, ${0.18 + t * 0.82})`
                : EMPTY;
            const active =
              selectedFico?.length === 1 &&
              selectedLtv?.length === 1 &&
              selectedFico[0] === cell.fico &&
              selectedLtv[0] === cell.ltv;
            return (
              <button
                key={`${cell.fico}-${cell.ltv}`}
                type="button"
                className={`collat-heatmap-cell${active ? " is-active" : ""}`}
                style={{ background: bg, color: t > 0.45 ? "#111" : TEXT }}
                title={`FICO ${cell.fico} × LTV ${cell.ltv}: ${fmtUpbShort(cell.upb)} · ${cell.loan_count} Loans`}
                onClick={() => onSelectCell?.(cell.fico, cell.ltv)}
              >
                {cell.loan_count ? cell.loan_count : ""}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const explorerCols = [
  {
    headerName: "Loan ID",
    field: "loan_id",
    minWidth: 110,
    pinned: "left",
  },
  {
    headerName: "Cohort",
    field: "cohort_display",
    minWidth: 120,
  },
  moneyCol("current_loan_amount", "UPB"),
  {
    headerName: "FICO",
    field: "original_fico",
    width: 80,
    valueFormatter: (p) => (p.value == null ? "" : String(p.value)),
  },
  ltvCol("original_ltv", "Orig LTV", 90),
  ltvCol("current_ltv", "Curr LTV", 90),
  ltvCol("original_cltv", "Orig CLTV", 90),
  ltvCol("current_cltv", "Curr CLTV", 90),
  {
    headerName: "Rate",
    field: "current_interest_rate",
    width: 80,
    valueFormatter: (p) => fmtPct(p.value, 2),
  },
  {
    headerName: "RI",
    field: "refinance_incentive",
    width: 70,
    valueFormatter: (p) => fmtNum(p.value, 2),
  },
  { headerName: "State", field: "state", width: 70 },
  { headerName: "Documentation", field: "documentation_type", minWidth: 140 },
  { headerName: "Occupancy", field: "occupancy", minWidth: 100 },
  { headerName: "Purpose", field: "loan_purpose", minWidth: 120 },
  {
    headerName: "DTI",
    field: "originator_dti",
    width: 80,
    valueFormatter: (p) => fmtPct(p.value, 1),
  },
  {
    headerName: "DSCR",
    field: "dscr",
    width: 80,
    valueFormatter: (p) => fmtNum(p.value, 2),
  },
  intCol("days_delinquent", "Days DQ"),
  intCol("risk_flag_count", "Flags"),
  {
    headerName: "Risk Flags",
    field: "risk_flags",
    minWidth: 220,
    flex: 1,
    valueFormatter: (p) => (Array.isArray(p.value) ? p.value.join("; ") : ""),
  },
];

export default function LoanLevelCollateral() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [loans, setLoans] = useState([]);
  const [cohortsMeta, setCohortsMeta] = useState([]);
  const [sectionRefs, setSectionRefs] = useState({});
  const [filters, setFilters] = useState(emptyFilters);
  const [ltvMode, setLtvMode] = useState("original");
  const [metric, setMetric] = useState("upb");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(apiUrl("/api/asf/collateral?include_loans=true"));
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        if (cancelled) return;
        setLoans(data.loans || []);
        setCohortsMeta(data.cohorts || []);
        setSectionRefs(data.section_refs || {});
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () => applyFilters(loans, filters, ltvMode),
    [loans, filters, ltvMode]
  );

  const kpis = useMemo(() => {
    const upb = filtered.reduce((s, l) => s + (Number(l.current_loan_amount) || 0), 0);
    return {
      loan_count: filtered.length,
      upb,
      wac: upbWeightedMean(filtered, "current_interest_rate"),
      wam: upbWeightedMean(filtered, "remaining_term"),
      wa_fico: upbWeightedMean(filtered, "original_fico"),
      wa_ltv: upbWeightedMean(filtered, "original_ltv"),
      wa_cltv: upbWeightedMean(filtered, "original_cltv"),
      wa_current_ltv: upbWeightedMean(filtered, "current_ltv"),
      wa_dti: upbWeightedMean(filtered, "originator_dti"),
      wa_dscr: upbWeightedMean(filtered, "dscr"),
      wa_ri: upbWeightedMean(filtered, "refinance_incentive"),
      wa_age: upbWeightedMean(filtered, "loan_age_months"),
      flagged_loan_count: filtered.filter((l) => (l.risk_flags || []).length).length,
    };
  }, [filtered]);

  const obs = useMemo(() => liveObservations(filtered, kpis), [filtered, kpis]);

  const ltvField =
    ltvMode === "current" ? "ltv_band_current" : "ltv_band_original";
  const ficoRows = useMemo(
    () => aggregate(filtered, "fico_band", FICO_ORDER),
    [filtered]
  );
  const ltvRows = useMemo(
    () => aggregate(filtered, ltvField, LTV_ORDER),
    [filtered, ltvField]
  );
  const dtiRows = useMemo(
    () => aggregate(filtered, "dti_band", null, { hideMissing: true }),
    [filtered]
  );
  const dscrRows = useMemo(
    () => aggregate(filtered, "dscr_band", null, { hideMissing: true }),
    [filtered]
  );
  const docRows = useMemo(
    () => aggregate(filtered, "documentation_type"),
    [filtered]
  );
  const occRows = useMemo(() => aggregate(filtered, "occupancy"), [filtered]);
  const purposeRows = useMemo(
    () => aggregate(filtered, "loan_purpose"),
    [filtered]
  );
  const propRows = useMemo(
    () => aggregate(filtered, "property_type"),
    [filtered]
  );
  const ageRows = useMemo(() => {
    const AGE_ORDER = ["0-6", "7-12", "13-24", "25+", "missing"];
    const base = aggregate(filtered, "age_band", AGE_ORDER);
    return base.map((row) => {
      const inBand = filtered.filter((l) => (l.age_band || "missing") === row.bucket);
      return { ...row, wac: upbWeightedMean(inBand, "current_interest_rate") };
    });
  }, [filtered]);
  const stateRows = useMemo(() => aggregate(filtered, "state"), [filtered]);
  const heatCells = useMemo(
    () => buildHeatmap(filtered, ltvMode),
    [filtered, ltvMode]
  );
  const couponRows = useMemo(() => {
    const bands = [
      ["<6%", 0, 0.06],
      ["6-7%", 0.06, 0.07],
      ["7-8%", 0.07, 0.08],
      ["8-9%", 0.08, 0.09],
      ["9%+", 0.09, 1],
    ];
    const map = Object.fromEntries(
      bands.map(([b]) => [b, { bucket: b, loan_count: 0, upb: 0 }])
    );
    for (const loan of filtered) {
      const r = Number(loan.current_interest_rate);
      let label = "missing";
      if (Number.isFinite(r)) {
        label =
          bands.find(([, lo, hi]) => r >= lo && r < hi)?.[0] || bands.at(-1)[0];
      }
      if (!map[label]) map[label] = { bucket: label, loan_count: 0, upb: 0 };
      map[label].loan_count += 1;
      map[label].upb += Number(loan.current_loan_amount) || 0;
    }
    return bands.map(([b]) => map[b]).filter((r) => r.loan_count);
  }, [filtered]);
  const riRows = useMemo(() => {
    const bands = [
      ["<0", -100, 0],
      ["0-1", 0, 1],
      ["1-2", 1, 2],
      ["2+", 2, 100],
    ];
    const map = Object.fromEntries(
      bands.map(([b]) => [b, { bucket: b, loan_count: 0, upb: 0 }])
    );
    for (const loan of filtered) {
      const r = Number(loan.refinance_incentive);
      let label = "missing";
      if (Number.isFinite(r)) {
        label =
          bands.find(([, lo, hi]) => r >= lo && r < hi)?.[0] || bands.at(-1)[0];
      }
      if (!map[label]) map[label] = { bucket: label, loan_count: 0, upb: 0 };
      map[label].loan_count += 1;
      map[label].upb += Number(loan.current_loan_amount) || 0;
    }
    return bands.map(([b]) => map[b]).filter((r) => r.loan_count);
  }, [filtered]);

  const activeFilterCount =
    filters.cohorts.length +
    filters.ficoBands.length +
    filters.ltvBands.length +
    filters.states.length +
    filters.documentationTypes.length +
    filters.occupancies.length +
    filters.purposes.length +
    filters.propertyTypes.length +
    filters.dtiBands.length +
    filters.dscrBands.length +
    filters.ageBands.length +
    filters.couponBands.length +
    filters.riBands.length +
    (filters.riskOnly ? 1 : 0);

  const resetFilters = useCallback(() => setFilters(emptyFilters()), []);

  const activeChips = useMemo(() => {
    const chips = [];
    const cohortLabel = Object.fromEntries(
      (cohortsMeta || []).map((c) => [c.id, c.label])
    );
    for (const id of filters.cohorts) {
      chips.push({
        key: `cohort:${id}`,
        label: cohortLabel[id] || id,
        clear: () =>
          setFilters((f) => ({
            ...f,
            cohorts: f.cohorts.filter((x) => x !== id),
          })),
      });
    }
    const add = (arr, prefix, clearKey) => {
      for (const v of arr) {
        chips.push({
          key: `${prefix}:${v}`,
          label: `${prefix} ${v}`,
          clear: () =>
            setFilters((f) => ({
              ...f,
              [clearKey]: f[clearKey].filter((x) => x !== v),
            })),
        });
      }
    };
    add(filters.ficoBands, "FICO", "ficoBands");
    add(filters.ltvBands, "LTV", "ltvBands");
    add(filters.states, "State", "states");
    add(filters.documentationTypes, "Doc", "documentationTypes");
    add(filters.occupancies, "Occ", "occupancies");
    add(filters.purposes, "Purpose", "purposes");
    add(filters.propertyTypes, "Prop", "propertyTypes");
    add(filters.dtiBands, "DTI", "dtiBands");
    add(filters.dscrBands, "DSCR", "dscrBands");
    add(filters.ageBands, "Age", "ageBands");
    add(filters.couponBands, "Coupon", "couponBands");
    add(filters.riBands, "RI", "riBands");
    if (filters.riskOnly) {
      chips.push({
        key: "risk",
        label: "Flagged Only",
        clear: () => setFilters((f) => ({ ...f, riskOnly: false })),
      });
    }
    return chips;
  }, [filters, cohortsMeta]);

  if (loading) return <p className="muted">Loading Collateral Analysis…</p>;
  if (error)
    return <StatusBanner tone="error">Collateral: {error}</StatusBanner>;

  const metricKey = metric === "loans" ? "loan_count" : "upb";
  const cohortOptions = cohortsMeta.length
    ? cohortsMeta
    : [
        { id: "low LTV and weak refinance incentive", label: "LLTV Weak RI" },
        { id: "high LTV and strong refinance incentive", label: "HLTV Strong RI" },
        { id: "high LTV and weak refinance incentive", label: "HLTV Weak RI" },
      ];

  return (
    <section className="section section-fill section-collateral">
      <div className="collat-kpi-row" role="toolbar" aria-label="Collateral KPIs">
        <button
          type="button"
          className="collat-kpi is-active"
          aria-label="Selected Loans"
          onClick={resetFilters}
          title="Reset Filters"
        >
          <span className="collat-kpi-label">Selected Loans</span>
          <span className="collat-kpi-value">
            {kpis.loan_count.toLocaleString()}
          </span>
        </button>
        <div className="collat-kpi" aria-label="Selected UPB">
          <span className="collat-kpi-label">Selected UPB</span>
          <span className="collat-kpi-value">{fmtUpbShort(kpis.upb)}</span>
        </div>
        <div className="collat-kpi" aria-label="WAC" title="UPB-Weighted Average Coupon">
          <span className="collat-kpi-label">WAC</span>
          <span className="collat-kpi-value">
            {kpis.wac != null ? `${(kpis.wac * 100).toFixed(2)}%` : "—"}
          </span>
        </div>
        <div className="collat-kpi" aria-label="WA FICO">
          <span className="collat-kpi-label">WA FICO</span>
          <span className="collat-kpi-value">
            {kpis.wa_fico != null ? kpis.wa_fico.toFixed(0) : "—"}
          </span>
        </div>
        <div className="collat-kpi" aria-label="WA LTV">
          <span className="collat-kpi-label">
            {ltvMode === "current" ? "WA Curr LTV" : "WA Orig LTV"}
          </span>
          <span className="collat-kpi-value">
            {ltvMode === "current"
              ? kpis.wa_current_ltv != null
                ? fmtLtv(kpis.wa_current_ltv)
                : "—"
              : kpis.wa_ltv != null
                ? fmtLtv(kpis.wa_ltv)
                : "—"}
          </span>
        </div>
        <button
          type="button"
          className={`collat-kpi${filters.riskOnly ? " is-active" : ""}`}
          aria-label="Flagged Loans"
          title="Toggle Flagged Only"
          onClick={() =>
            setFilters((f) => ({ ...f, riskOnly: !f.riskOnly }))
          }
        >
          <span className="collat-kpi-label">Flagged</span>
          <span className="collat-kpi-value">
            {kpis.flagged_loan_count.toLocaleString()}
          </span>
        </button>
      </div>

      <div className="collat-filter-row" role="toolbar" aria-label="Collateral Filters">
        <div className="collat-cohort-chips" role="group" aria-label="Cohort Filter">
          <button
            type="button"
            className={`collat-chip${!filters.cohorts.length ? " is-active" : ""}`}
            onClick={() => setFilters((f) => ({ ...f, cohorts: [] }))}
          >
            All Cohorts
          </button>
          {cohortOptions.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`collat-chip${
                filters.cohorts.includes(c.id) ? " is-active" : ""
              }`}
              onClick={() =>
                setFilters((f) => ({
                  ...f,
                  cohorts: toggleInList(f.cohorts, c.id),
                }))
              }
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="collat-filter-actions">
          <label className="field-inline collat-ltv-mode">
            <span>LTV</span>
            <select
              className="select"
              value={ltvMode}
              onChange={(e) => setLtvMode(e.target.value)}
              aria-label="LTV Mode"
            >
              <option value="original">Original</option>
              <option value="current">Current (Derived)</option>
            </select>
          </label>
          <div className="collat-toggle" role="group" aria-label="Metric">
            <button
              type="button"
              className={`collat-chip${metric === "upb" ? " is-active" : ""}`}
              onClick={() => setMetric("upb")}
            >
              UPB
            </button>
            <button
              type="button"
              className={`collat-chip${metric === "loans" ? " is-active" : ""}`}
              onClick={() => setMetric("loans")}
            >
              Loans
            </button>
          </div>
          <button
            type="button"
            className="collat-chip collat-reset"
            onClick={resetFilters}
            disabled={!activeFilterCount}
          >
            Reset Filters{activeFilterCount ? ` (${activeFilterCount})` : ""}
          </button>
        </div>
      </div>

      {activeChips.length > 0 ? (
        <div className="collat-active-filters" aria-label="Active Filters">
          {activeChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              className="collat-active-chip"
              onClick={chip.clear}
              title="Remove Filter"
            >
              {chip.label} ×
            </button>
          ))}
        </div>
      ) : null}

      <div className="collat-grid">
        <div className="collat-panel">
          <SectionHead title="FICO Distribution" refsKey="fico" sectionRefs={sectionRefs} />
          <Observation text={obs.fico} />
          <DistBar
            rows={ficoRows}
            selected={filters.ficoBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                ficoBands: toggleInList(f.ficoBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead
            title={
              ltvMode === "current"
                ? "Current LTV Distribution"
                : "Original LTV Distribution"
            }
            refsKey="ltv"
            sectionRefs={sectionRefs}
          />
          <Observation text={obs.ltv} />
          <DistBar
            rows={ltvRows}
            selected={filters.ltvBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                ltvBands: toggleInList(f.ltvBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel collat-panel-wide">
          <SectionHead title="FICO × LTV Heatmap" refsKey="heatmap" sectionRefs={sectionRefs} />
          <Observation text={obs.heatmap} />
          <Heatmap
            cells={heatCells}
            selectedFico={filters.ficoBands}
            selectedLtv={filters.ltvBands}
            onSelectFico={(b) =>
              setFilters((f) => ({
                ...f,
                ficoBands: toggleInList(f.ficoBands, b),
              }))
            }
            onSelectLtv={(b) =>
              setFilters((f) => ({
                ...f,
                ltvBands: toggleInList(f.ltvBands, b),
              }))
            }
            onSelectCell={(fico, ltv) =>
              setFilters((f) => {
                const same =
                  f.ficoBands.length === 1 &&
                  f.ltvBands.length === 1 &&
                  f.ficoBands[0] === fico &&
                  f.ltvBands[0] === ltv;
                return {
                  ...f,
                  ficoBands: same ? [] : [fico],
                  ltvBands: same ? [] : [ltv],
                };
              })
            }
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="DTI Histogram" refsKey="dti_dscr" sectionRefs={sectionRefs} />
          <Observation text={obs.dti_dscr} />
          <DistBar
            rows={dtiRows}
            selected={filters.dtiBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                dtiBands: toggleInList(f.dtiBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="DSCR Histogram" refsKey="dti_dscr" sectionRefs={sectionRefs} />
          <DistBar
            rows={dscrRows}
            selected={filters.dscrBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                dscrBands: toggleInList(f.dscrBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="Documentation Mix" refsKey="documentation" sectionRefs={sectionRefs} />
          <Observation text={obs.documentation} />
          <DistBar
            rows={docRows}
            horizontal
            selected={filters.documentationTypes}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                documentationTypes: toggleInList(f.documentationTypes, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead
            title="Occupancy"
            refsKey="mix"
            sectionRefs={sectionRefs}
          />
          <Observation text={obs.mix} />
          <DistBar
            rows={occRows}
            selected={filters.occupancies}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                occupancies: toggleInList(f.occupancies, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="Loan Purpose" refsKey="mix" sectionRefs={sectionRefs} />
          <DistBar
            rows={purposeRows}
            selected={filters.purposes}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                purposes: toggleInList(f.purposes, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="Property Type" refsKey="mix" sectionRefs={sectionRefs} />
          <DistBar
            rows={propRows}
            horizontal
            selected={filters.propertyTypes}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                propertyTypes: toggleInList(f.propertyTypes, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="Coupon Distribution" refsKey="coupon" sectionRefs={sectionRefs} />
          <Observation text={obs.coupon} />
          <DistBar
            rows={couponRows}
            selected={filters.couponBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                couponBands: toggleInList(f.couponBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel">
          <SectionHead title="Refinance Incentive" refsKey="coupon" sectionRefs={sectionRefs} />
          <DistBar
            rows={riRows}
            selected={filters.riBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                riBands: toggleInList(f.riBands, b),
              }))
            }
            metric={metricKey}
          />
        </div>

        <div className="collat-panel collat-panel-wide">
          <SectionHead title="Seasoning · UPB + WAC" refsKey="coupon" sectionRefs={sectionRefs} />
          <AgeWacChart
            rows={ageRows}
            selected={filters.ageBands}
            onSelect={(b) =>
              setFilters((f) => ({
                ...f,
                ageBands: toggleInList(f.ageBands, b),
              }))
            }
          />
        </div>

        <div className="collat-panel collat-panel-wide">
          <SectionHead title="US Map + Top 10 States" refsKey="geo" sectionRefs={sectionRefs} />
          <Observation text={obs.geo} />
          <div className="collat-geo">
            <StateChoropleth
              rows={stateRows}
              metric={metric === "loans" ? "loans" : "upb"}
              selected={filters.states[0] || null}
              onSelect={(abbr) =>
                setFilters((f) => ({
                  ...f,
                  states: toggleInList(f.states, abbr),
                }))
              }
              fmtTip={(v) =>
                metric === "loans" ? Number(v).toLocaleString() : fmtUpbShort(v)
              }
            />
            <ol className="collat-top-states">
              {stateRows.slice(0, 10).map((row, i) => (
                <li key={row.bucket}>
                  <button
                    type="button"
                    className={`collat-top-state${
                      filters.states.includes(row.bucket) ? " is-active" : ""
                    }`}
                    onClick={() =>
                      setFilters((f) => ({
                        ...f,
                        states: toggleInList(f.states, row.bucket),
                      }))
                    }
                  >
                    <span>
                      {i + 1}. {row.bucket}
                    </span>
                    <span>
                      {metric === "loans"
                        ? row.loan_count.toLocaleString()
                        : fmtUpbShort(row.upb)}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="collat-panel collat-panel-full">
          <SectionHead title="Loan Exception Explorer" refsKey="explorer" sectionRefs={sectionRefs} />
          <Observation text={obs.explorer} />
          <DataGrid
            rowData={filtered}
            columnDefs={explorerCols}
            getRowId={(p) => String(p.data.loan_id)}
            heightClass="grid-wrap-collateral"
            exportName="collateral-exceptions"
          />
        </div>
      </div>
    </section>
  );
}
