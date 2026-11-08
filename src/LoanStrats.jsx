/**
 * Loan Strats — loan-level pool charts (no cohort UI).
 */
import { useEffect, useMemo, useState } from "react";
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
  FONT,
  PaneSpinner,
  fmtInt,
  fmtLtv,
  fmtNum,
  pushToast,
} from "./cashflowGrid";
import { StateChoropleth } from "./UsChoropleth";
import { MARKET_RATE_REF } from "./marketRateRef";

const AMBER = "#FD9D24";
const MUTED = "#808080";
const TEXT = "#FCFCFC";
const GRID = "#323232";
const EMPTY = "#121212";

/** Dark tip + soft amber hover band (Recharts default cursor is a bright white strip). */
const TIP_STYLE = {
  background: "#0C0C0C",
  border: "1px solid #323232",
  borderRadius: 0,
  fontSize: 11,
  color: TEXT,
  fontFamily: FONT,
  boxShadow: "none",
};
const TIP_CURSOR = { fill: "rgba(253, 157, 36, 0.12)", stroke: "none" };
const TIP_LABEL = { color: TEXT };
const TIP_ITEM = { color: TEXT };

/** Bloomberg-ish muted fills — cycle by category; selected stays bright amber. */
const BAR_PALETTE = [
  "#C4A574", // sand
  "#B87333", // copper
  "#8FA3B0", // steel
  "#A67C52", // bronze
  "#7A8B6E", // olive
  "#D4A017", // gold
  "#6B7C8A", // slate
  "#9A6B5C", // terracotta
  "#8B7355", // taupe
  "#5C8A8A", // teal muted
  "#B8860B", // darkgold
  "#7D6B8A", // mauve
];

function barFill(bucket, index, selected) {
  if (selected?.includes(bucket)) return AMBER;
  return BAR_PALETTE[index % BAR_PALETTE.length];
}

const FICO_ORDER = ["<660", "660-699", "700-739", "740-779", "780+", "missing"];
const LTV_ORDER = ["<60", "60-70", "70-80", "80-90", "90+", "missing"];
const DTI_ORDER = ["<30", "30-36", "36-43", "43-50", "50+", "missing"];
const DSCR_ORDER = ["<1.0", "1.0-1.25", "1.25-1.5", "1.5+", "missing"];

function fmtUpbShort(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

/** Heatmap cell UPB — millions/k without `$` (e.g. 1.5M). */
function fmtHeatUpb(v) {
  if (v == null || Number.isNaN(Number(v)) || !Number(v)) return "0";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(0)}k`;
  return n.toFixed(0);
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
  };
}

function applyFilters(loans, filters) {
  return (loans || []).filter((loan) => {
    if (filters.ficoBands.length && !filters.ficoBands.includes(loan.fico_band))
      return false;
    if (
      filters.ltvBands.length &&
      !filters.ltvBands.includes(loan.ltv_band_current)
    )
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
    return true;
  });
}

/** UPB-weighted mean: Σ(value × current_loan_amount) / Σ(current_loan_amount). Not a simple avg. */
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

/** WAC KPI — 2 decimals so UPB-weighting is visible vs a rounded simple avg. */
function fmtWacKpi(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const fixed = (Number(v) * 100).toFixed(2);
  return `${fixed.replace(/\.?0+$/, "")}%`;
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

function buildHeatmap(loans) {
  const cells = new Map();
  for (const loan of loans) {
    const fico = loan.fico_band || "missing";
    let ltvBand = "missing";
    const v = Number(loan.current_ltv);
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

/** Compact Y labels for horizontal DistBars (full name stays in tooltip). */
const SHORT_BUCKET_LABEL = {
  "Bank statement 12m": "Bank 12m",
  "Bank statement 24m": "Bank 24m",
  "Single family / PUD": "SF / PUD",
  "Manufactured / other": "Mfg / other",
};

function shortBucketLabel(v) {
  if (v == null) return "";
  const s = String(v);
  return SHORT_BUCKET_LABEL[s] || s;
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
        margin={
          horizontal
            ? { top: 0, right: 4, left: 4, bottom: 0 }
            : { top: 2, right: 4, left: 0, bottom: 0 }
        }
        barCategoryGap={horizontal ? "12%" : "18%"}
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
              width={92}
              interval={0}
              tick={{ fill: MUTED, fontSize: 10, fontFamily: FONT }}
              tickFormatter={shortBucketLabel}
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
          cursor={TIP_CURSOR}
          contentStyle={TIP_STYLE}
          labelStyle={TIP_LABEL}
          itemStyle={TIP_ITEM}
          wrapperStyle={{ outline: "none" }}
          formatter={(v) =>
            metric === "loan_count" ? Number(v).toLocaleString() : fmtUpbShort(v)
          }
          labelFormatter={(label) => String(label)}
        />
        <Bar
          dataKey={valueKey}
          cursor="pointer"
          maxBarSize={horizontal ? 36 : 48}
          onClick={(d) => d?.bucket != null && onSelect?.(d.bucket)}
        >
          {data.map((row, i) => (
            <Cell key={row.bucket} fill={barFill(row.bucket, i, selected)} />
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
            margin={{ top: 4, right: 8, left: 0, bottom: 2 }}
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
              cursor={TIP_CURSOR}
              contentStyle={TIP_STYLE}
              labelStyle={TIP_LABEL}
              itemStyle={TIP_ITEM}
              wrapperStyle={{ outline: "none" }}
              formatter={(v, name) =>
                name === "wac"
                  ? `${(Number(v) * 100).toFixed(2)}%`
                  : fmtUpbShort(v)
              }
            />
            <Bar
              yAxisId="upb"
              dataKey="upb"
              name="UPB"
              cursor="pointer"
              onClick={(d) => d?.bucket != null && onSelect?.(d.bucket)}
            >
              {data.map((row, i) => (
                <Cell key={row.bucket} fill={barFill(row.bucket, i, selected)} />
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
  /* Flat grid children (no display:contents rows) so the last FICO band is never clipped. */
  return (
    <div className="collat-heatmap strats-heatmap" role="img" aria-label="FICO By LTV Heatmap">
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
      {grid.map((row, i) => {
        const fico = ficoLabels[i];
        return [
          <button
            key={`y-${fico}`}
            type="button"
            className={`collat-heatmap-axis collat-heatmap-y${
              selectedFico?.includes(fico) ? " is-active" : ""
            }`}
            onClick={() => onSelectFico?.(fico)}
          >
            {fico}
          </button>,
          ...row.map((cell) => {
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
            const label =
              cell.loan_count || cell.upb
                ? `${cell.loan_count || 0} / ${fmtHeatUpb(cell.upb)}`
                : "";
            return (
              <button
                key={`${cell.fico}-${cell.ltv}`}
                type="button"
                className={`collat-heatmap-cell${active ? " is-active" : ""}`}
                style={{ background: bg, color: t > 0.45 ? "#111" : TEXT }}
                title={`FICO ${cell.fico} × LTV ${cell.ltv}: ${cell.loan_count || 0} loans · ${fmtUpbShort(cell.upb)}`}
                onClick={() => onSelectCell?.(cell.fico, cell.ltv)}
              >
                {label}
              </button>
            );
          }),
        ];
      })}
    </div>
  );
}

/** Session cache — revisiting Strats should not re-download the tape. */
let stratsCache = null;
let stratsInflight = null;

async function loadStratsCollateral() {
  if (stratsCache) return stratsCache;
  if (stratsInflight) return stratsInflight;
  stratsInflight = (async () => {
    const collatRes = await fetch(
      apiUrl("/api/asf/collateral?include_loans=true&slim=true")
    );
    if (!collatRes.ok) throw new Error(await collatRes.text());
    const data = await collatRes.json();
    stratsCache = {
      loans: data.loans || [],
      sectionRefs: data.section_refs || {},
    };
    return stratsCache;
  })();
  try {
    return await stratsInflight;
  } finally {
    stratsInflight = null;
  }
}

/** Warm Strats tape in the background after first paint (call from App). */
export function prefetchLoanStrats() {
  loadStratsCollateral().catch(() => {
    /* toast only when the pane opens */
  });
}

export default function LoanStrats() {
  const [loading, setLoading] = useState(!stratsCache);
  const [loans, setLoans] = useState(stratsCache?.loans || []);
  const [sectionRefs, setSectionRefs] = useState(
    stratsCache?.sectionRefs || {}
  );
  const [filters, setFilters] = useState(emptyFilters);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!stratsCache) setLoading(true);
      try {
        const data = await loadStratsCollateral();
        if (cancelled) return;
        setLoans(data.loans);
        setSectionRefs(data.sectionRefs);
      } catch (err) {
        if (!cancelled) {
          setLoans([]);
          pushToast(`Loan Strats: ${err.message || String(err)}`, "error");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () => applyFilters(loans, filters),
    [loans, filters]
  );

  const kpis = useMemo(() => {
    const upb = filtered.reduce((s, l) => s + (Number(l.current_loan_amount) || 0), 0);
    return {
      loan_count: filtered.length,
      upb,
      wac: upbWeightedMean(filtered, "current_interest_rate"),
      wam: upbWeightedMean(filtered, "remaining_term"),
      wa_fico: upbWeightedMean(filtered, "original_fico"),
      wa_cltv: upbWeightedMean(filtered, "current_cltv"),
      wa_current_ltv: upbWeightedMean(filtered, "current_ltv"),
      wa_dti: upbWeightedMean(filtered, "originator_dti"),
      wa_dscr: upbWeightedMean(filtered, "dscr"),
      wa_ri: upbWeightedMean(filtered, "refinance_incentive"),
      wa_age: upbWeightedMean(filtered, "loan_age_months"),
    };
  }, [filtered]);

  const ficoRows = useMemo(
    () => aggregate(filtered, "fico_band", FICO_ORDER),
    [filtered]
  );
  const ltvRows = useMemo(
    () => aggregate(filtered, "ltv_band_current", LTV_ORDER),
    [filtered]
  );
  const dtiRows = useMemo(
    () => aggregate(filtered, "dti_band", DTI_ORDER, { hideMissing: true }),
    [filtered]
  );
  const dscrRows = useMemo(
    () => aggregate(filtered, "dscr_band", DSCR_ORDER, { hideMissing: true }),
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
    () => buildHeatmap(filtered),
    [filtered]
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

  const activeChips = useMemo(() => {
    const chips = [];
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
    return chips;
  }, [filters]);

  if (loading) return <PaneSpinner label="Loading Loan Strats…" />;

  return (
    <section className="section section-fill section-collateral section-strats">
      <div className="strats-topbar">
        <div className="strats-topbar-start">
          {activeChips.length > 0 ? (
            <div className="strats-active-chips" aria-label="Active Filters">
              {activeChips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="strats-chip"
                  onClick={chip.clear}
                  title="Remove Filter"
                >
                  {chip.label} ×
                </button>
              ))}
            </div>
          ) : (
            <div className="strats-active-chips" aria-hidden="true" />
          )}
          <p className="strats-tape-meta muted" aria-label="Mortgage Ref Rate">
            <span title={MARKET_RATE_REF.title}>
              {MARKET_RATE_REF.caption}
            </span>
          </p>
        </div>

        <div
          className="qc-kpi-strip strats-kpi-strip"
          role="toolbar"
          aria-label="Loan Strats KPIs"
        >
          <div
            className="qc-kpi"
            aria-label="Total Loans"
            title="Loans In Current Filter"
          >
            <span className="qc-kpi-label">Total Loans</span>
            <span className="qc-kpi-value">{fmtInt(kpis.loan_count)}</span>
          </div>
          <div
            className="qc-kpi"
            aria-label="UPB"
            title="Current UPB In Filter"
          >
            <span className="qc-kpi-label">UPB</span>
            <span className="qc-kpi-value">{fmtUpbShort(kpis.upb)}</span>
          </div>
          <div
            className="qc-kpi"
            aria-label="Mortgage Ref Rate"
            title={MARKET_RATE_REF.title}
          >
            <span className="qc-kpi-label">Mort Ref</span>
            <span className="qc-kpi-value">
              {fmtWacKpi(MARKET_RATE_REF.rate)}
            </span>
          </div>
          <div
            className="qc-kpi"
            aria-label="WAC"
            title="Pool UPB-Weighted Average Coupon (not the market ref rate)"
          >
            <span className="qc-kpi-label">WAC</span>
            <span className="qc-kpi-value">
              {kpis.wac != null ? fmtWacKpi(kpis.wac) : "—"}
            </span>
          </div>
          <div
            className="qc-kpi"
            aria-label="WA FICO"
            title="UPB-Weighted Average FICO"
          >
            <span className="qc-kpi-label">WA FICO</span>
            <span className="qc-kpi-value">
              {kpis.wa_fico != null ? fmtInt(kpis.wa_fico) : "—"}
            </span>
          </div>
          <div
            className="qc-kpi"
            aria-label="WA CLTV"
            title="UPB-Weighted Average CLTV"
          >
            <span className="qc-kpi-label">WA CLTV</span>
            <span className="qc-kpi-value">
              {kpis.wa_cltv != null ? fmtLtv(kpis.wa_cltv) : "—"}
            </span>
          </div>
          <div
            className="qc-kpi"
            aria-label="WA RI"
            title="UPB-Weighted Average Refinance Incentive (note − 30Y PMMS)"
          >
            <span className="qc-kpi-label">WA RI</span>
            <span className="qc-kpi-value">
              {kpis.wa_ri != null ? fmtNum(kpis.wa_ri, 2) : "—"}
            </span>
          </div>
        </div>
      </div>

      <div className="strats-body">
        <div className="strats-charts collat-grid">
          <div className="collat-panel strats-panel-quad">
            <SectionHead title="FICO" refsKey="fico" sectionRefs={sectionRefs} />
            <DistBar
              rows={ficoRows}
              selected={filters.ficoBands}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  ficoBands: toggleInList(f.ficoBands, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
            <SectionHead title="Current LTV" refsKey="ltv" sectionRefs={sectionRefs} />
            <DistBar
              rows={ltvRows}
              selected={filters.ltvBands}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  ltvBands: toggleInList(f.ltvBands, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
            <SectionHead title="DTI" refsKey="dti_dscr" sectionRefs={sectionRefs} />
            <DistBar
              rows={dtiRows}
              selected={filters.dtiBands}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  dtiBands: toggleInList(f.dtiBands, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
            <SectionHead title="Occupancy" refsKey="mix" sectionRefs={sectionRefs} />
            <DistBar
              rows={occRows}
              selected={filters.occupancies}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  occupancies: toggleInList(f.occupancies, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-half strats-row-start strats-heatmap-panel">
            <SectionHead title="FICO × LTV" refsKey="heatmap" sectionRefs={sectionRefs} />
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

          <div className="collat-panel strats-panel-half">
            <SectionHead title="Geography" refsKey="geo" sectionRefs={sectionRefs} />
            <div className="collat-geo">
              <StateChoropleth
                rows={stateRows}
                metric="upb"
                selected={filters.states[0] || null}
                onSelect={(abbr) =>
                  setFilters((f) => ({
                    ...f,
                    states: toggleInList(f.states, abbr),
                  }))
                }
                fmtTip={(v) => fmtUpbShort(v)}
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
                      <span>{fmtUpbShort(row.upb)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="collat-panel strats-panel-third">
            <SectionHead title="Documentation" refsKey="documentation" sectionRefs={sectionRefs} />
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
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-third">
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
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-third">
            <SectionHead title="Coupon" refsKey="coupon" sectionRefs={sectionRefs} />
            <DistBar
              rows={couponRows}
              selected={filters.couponBands}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  couponBands: toggleInList(f.couponBands, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
            <SectionHead title="DSCR" refsKey="dti_dscr" sectionRefs={sectionRefs} />
            <DistBar
              rows={dscrRows}
              selected={filters.dscrBands}
              onSelect={(b) =>
                setFilters((f) => ({
                  ...f,
                  dscrBands: toggleInList(f.dscrBands, b),
                }))
              }
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
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
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
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
              metric="upb"
            />
          </div>

          <div className="collat-panel strats-panel-quad">
            <SectionHead title="Seasoning" refsKey="coupon" sectionRefs={sectionRefs} />
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
        </div>
      </div>
    </section>
  );
}
