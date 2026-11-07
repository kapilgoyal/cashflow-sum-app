import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  Polygon,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import {
  DataGrid,
  DrillTrail,
  FONT,
  StatusBanner,
  fmtNum,
  fmtPct,
  intCol,
  moneyCol,
  pcaLabel,
  staLabel,
  withScenarioRowSpans,
} from "./cashflowGrid";
import { apiUrl } from "./apiBase";
import { StateChoropleth, Zip3Choropleth } from "./UsChoropleth";
import "./App.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const NAV = [
  { id: "asf", label: "Investor Tape" },
  { id: "qc", label: "Loan QC" },
  { id: "strat", label: "Stratification" },
  { id: "cohort", label: "Cohort" },
  { id: "scenarios", label: "Scenarios" },
  { id: "cashflow", label: "Cash Flow" },
  { id: "assumptions", label: "Assumptions" },
];

/** Standard mortgage strat cuts. chart: bar | hbar | pie | histogram | line | map | zip */
const STRAT_DIMS_BASE = [
  { id: "ltv_bucket", label: "LTV", chart: "histogram" },
  { id: "cltv_bucket", label: "CLTV", chart: "histogram" },
  { id: "fico_band", label: "FICO", chart: "histogram" },
  { id: "balance_band", label: "Balance", chart: "histogram" },
  { id: "orig_year", label: "Origination Year", chart: "line" },
  { id: "state", label: "State", chart: "map" },
  { id: "zip3", label: "ZIP3", chart: "zip" },
  { id: "documentation_type", label: "Documentation Type", chart: "hbar" },
  { id: "occupancy", label: "Occupancy", chart: "pie" },
  { id: "loan_purpose", label: "Loan Purpose", chart: "pie" },
  { id: "property_type", label: "Property Type", chart: "hbar" },
];

const STRAT_BAR_COLOR = "#001A41";
const STRAT_PIE_COLORS = [
  "#001A41",
  "#FD9D24",
  "#4A5F7A",
  "#1F8A44",
  "#8A9BB0",
  "#C51D46",
  "#0B4F9C",
  "#6B7C93",
];

function fmtUpbShort(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

function StratDimChart({ dim, rows, metric, selectedBucket, onBucketClick }) {
  const data = rows || [];
  const valueKey = metric === "loans" ? "loan_count" : "upb";
  const tick = {
    fill: "#4A5F7A",
    fontSize: 10,
    fontFamily: FONT,
  };
  const tipFmt = (v) =>
    metric === "loans" ? Number(v).toLocaleString() : fmtUpbShort(v);
  const metricLabel = metric === "loans" ? "Loans" : "UPB";
  const fireClick = (bucket) => {
    if (bucket == null || !onBucketClick) return;
    onBucketClick(String(bucket));
  };

  if (!data.length) {
    return <p className="muted strat-chart-empty">No Buckets</p>;
  }

  if (dim.chart === "map") {
    return (
      <StateChoropleth
        rows={data}
        metric={metric}
        selected={selectedBucket}
        onSelect={(abbr) => fireClick(abbr)}
        fmtTip={tipFmt}
      />
    );
  }

  if (dim.chart === "zip") {
    return (
      <Zip3Choropleth
        rows={data}
        metric={metric}
        selected={selectedBucket}
        onSelect={(z) => fireClick(z)}
        fmtTip={tipFmt}
      />
    );
  }

  if (dim.chart === "line") {
    const lineData = data.map((row) => ({
      ...row,
      wac_pct:
        row.wac != null && !Number.isNaN(Number(row.wac))
          ? Number(row.wac) * 100
          : row.avg_rate != null && !Number.isNaN(Number(row.avg_rate))
            ? Number(row.avg_rate) * 100
            : null,
    }));
    return (
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart
          data={lineData}
          margin={{ top: 8, right: 12, left: 0, bottom: 28 }}
        >
          <CartesianGrid stroke="#D0D7E2" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={tick}
            interval={0}
            angle={lineData.length > 6 ? -30 : 0}
            textAnchor={lineData.length > 6 ? "end" : "middle"}
            height={lineData.length > 6 ? 48 : 28}
            axisLine={{ stroke: "#8A9BB0" }}
            tickLine={{ stroke: "#8A9BB0" }}
          />
          <YAxis
            yAxisId="upb"
            tick={tick}
            tickFormatter={tipFmt}
            width={48}
            axisLine={{ stroke: "#8A9BB0" }}
            tickLine={{ stroke: "#8A9BB0" }}
          />
          <YAxis
            yAxisId="wac"
            orientation="right"
            tick={tick}
            tickFormatter={(v) => `${Number(v).toFixed(1)}%`}
            width={40}
            axisLine={{ stroke: "#8A9BB0" }}
            tickLine={{ stroke: "#8A9BB0" }}
          />
          <Tooltip
            formatter={(v, name) => {
              if (name === "WAC") return [`${Number(v).toFixed(2)}%`, "WAC"];
              return [tipFmt(v), metricLabel];
            }}
            labelFormatter={(l) => String(l)}
            contentStyle={{
              fontSize: 11,
              fontFamily: FONT,
              border: "1px solid #D0D7E2",
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, fontFamily: FONT }}
            iconSize={8}
          />
          <Bar
            yAxisId="upb"
            dataKey={valueKey}
            fill="#8A9BB0"
            name={metricLabel}
            radius={[1, 1, 0, 0]}
            cursor="pointer"
            onClick={(pt) => fireClick(pt?.bucket)}
          />
          <Line
            yAxisId="wac"
            type="monotone"
            dataKey="wac_pct"
            name="WAC"
            stroke="#FD9D24"
            strokeWidth={2}
            dot={{
              r: 3,
              fill: "#FD9D24",
              cursor: "pointer",
              onClick: (_e, payload) =>
                fireClick(payload?.payload?.bucket ?? payload?.bucket),
            }}
            activeDot={{
              r: 5,
              cursor: "pointer",
              onClick: (_e, payload) =>
                fireClick(payload?.payload?.bucket ?? payload?.bucket),
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  if (dim.chart === "pie") {
    return (
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey="bucket"
            cx="50%"
            cy="50%"
            innerRadius={42}
            outerRadius={72}
            paddingAngle={1}
            cursor="pointer"
            onClick={(_, idx) => fireClick(data[idx]?.bucket)}
          >
            {data.map((row, i) => (
              <Cell
                key={row.bucket}
                fill={STRAT_PIE_COLORS[i % STRAT_PIE_COLORS.length]}
                stroke={selectedBucket === row.bucket ? "#FD9D24" : undefined}
                strokeWidth={selectedBucket === row.bucket ? 2 : 0}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(v) => tipFmt(v)}
            contentStyle={{
              fontSize: 11,
              fontFamily: FONT,
              border: "1px solid #D0D7E2",
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, fontFamily: FONT }}
            iconSize={8}
          />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (dim.chart === "hbar") {
    const h = Math.min(280, Math.max(140, data.length * 22 + 28));
    return (
      <ResponsiveContainer width="100%" height={h}>
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 4, right: 12, left: 4, bottom: 4 }}
        >
          <CartesianGrid
            stroke="#D0D7E2"
            strokeDasharray="2 4"
            horizontal={false}
          />
          <XAxis
            type="number"
            tick={tick}
            tickFormatter={tipFmt}
            axisLine={{ stroke: "#8A9BB0" }}
            tickLine={{ stroke: "#8A9BB0" }}
          />
          <YAxis
            type="category"
            dataKey="bucket"
            width={92}
            tick={tick}
            axisLine={{ stroke: "#8A9BB0" }}
            tickLine={false}
          />
          <Tooltip
            formatter={(v) => tipFmt(v)}
            labelFormatter={(l) => String(l)}
            contentStyle={{
              fontSize: 11,
              fontFamily: FONT,
              border: "1px solid #D0D7E2",
            }}
          />
          <Bar
            dataKey={valueKey}
            fill={STRAT_BAR_COLOR}
            name={metricLabel}
            radius={[0, 1, 1, 0]}
            cursor="pointer"
            onClick={(pt) => fireClick(pt?.bucket)}
          >
            {data.map((row) => (
              <Cell
                key={row.bucket}
                fill={
                  selectedBucket === row.bucket ? "#FD9D24" : STRAT_BAR_COLOR
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  const isHistogram = dim.chart === "histogram";
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart
        data={data}
        margin={{ top: 8, right: 8, left: 0, bottom: 28 }}
        barCategoryGap={isHistogram ? "8%" : "20%"}
      >
        <CartesianGrid stroke="#D0D7E2" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="bucket"
          tick={tick}
          interval={0}
          angle={data.length > 6 ? -30 : 0}
          textAnchor={data.length > 6 ? "end" : "middle"}
          height={data.length > 6 ? 48 : 28}
          axisLine={{ stroke: "#8A9BB0" }}
          tickLine={{ stroke: "#8A9BB0" }}
        />
        <YAxis
          tick={tick}
          tickFormatter={tipFmt}
          width={48}
          axisLine={{ stroke: "#8A9BB0" }}
          tickLine={{ stroke: "#8A9BB0" }}
        />
        <Tooltip
          formatter={(v) => tipFmt(v)}
          labelFormatter={(l) => String(l)}
          contentStyle={{
            fontSize: 11,
            fontFamily: FONT,
            border: "1px solid #D0D7E2",
          }}
        />
        <Bar
          dataKey={valueKey}
          fill={isHistogram ? "#0B4F9C" : STRAT_BAR_COLOR}
          name={metricLabel}
          radius={isHistogram ? [0, 0, 0, 0] : [1, 1, 0, 0]}
          cursor="pointer"
          onClick={(pt) => fireClick(pt?.bucket)}
        >
          {data.map((row) => (
            <Cell
              key={row.bucket}
              fill={
                selectedBucket === row.bucket
                  ? "#FD9D24"
                  : isHistogram
                    ? "#0B4F9C"
                    : STRAT_BAR_COLOR
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function IconExportCsvMini({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M8 2v8.5M5.5 8.5 8 11l2.5-2.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3 13.5h10"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconCopyMini({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="5.25"
        y="5.25"
        width="7.5"
        height="8.5"
        rx="1"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M10.75 5.25V3.75A1.5 1.5 0 0 0 9.25 2.25H3.75A1.5 1.5 0 0 0 2.25 3.75v7.5A1.5 1.5 0 0 0 3.75 12.75h1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Match matplotlib CLUSTER_META order (0→1→2). No "RI" in labels. */
const CLUSTER_ORDER = [
  "low LTV and weak refinance incentive",
  "high LTV and strong refinance incentive",
  "high LTV and weak refinance incentive",
];
const CLUSTER_COLORS = {
  "low LTV and weak refinance incentive": "#1f77b4",
  "high LTV and strong refinance incentive": "#ff7f0e",
  "high LTV and weak refinance incentive": "#2ca02c",
};
const CLUSTER_FALLBACK_COUNTS = {
  "low LTV and weak refinance incentive": 339,
  "high LTV and strong refinance incentive": 329,
  "high LTV and weak refinance incentive": 375,
};

const X_DOMAIN = [0.28, 0.92];
const Y_DOMAIN = [-2.4, 3.2];
const X_TICKS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
const Y_TICKS = [-2, -1, 0, 1, 2, 3];
const POINT_SIZE = 28;
const OFF_AXIS_FEATURES = ["Documentation", "Remaining Term"];

const LS_CLUSTER_KEY = "cashflow.clusterFilter";
const LS_GRID_KEY = "cashflow.agGridState";
const LS_NAV_KEY = "cashflow.navPane";
const LS_NAV_COLLAPSE_KEY = "cashflow.navCollapsed";

const NAV_SHORT = {
  asf: "Tape",
  qc: "QC",
  strat: "Strat",
  cohort: "Cohort",
  scenarios: "Scen",
  cashflow: "CF",
  assumptions: "Asm",
};

function readClusterFilter() {
  try {
    const v = localStorage.getItem(LS_CLUSTER_KEY);
    if (v === "all" || CLUSTER_ORDER.includes(v)) return v;
  } catch {
    /* ignore */
  }
  return "all";
}

function isNarrowViewport() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 720px)").matches
  );
}

function readNavCollapsed() {
  try {
    const v = localStorage.getItem(LS_NAV_COLLAPSE_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return isNarrowViewport();
}

function readNav() {
  try {
    const v = localStorage.getItem(LS_NAV_KEY);
    if (NAV.some((n) => n.id === v)) return v;
    if (v === "loan") return "cohort";
  } catch {
    /* ignore */
  }
  return "asf";
}

function readGridState() {
  try {
    const raw = localStorage.getItem(LS_GRID_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

function saveGridState(api) {
  if (!api) return;
  try {
    const payload = {
      columnState: api.getColumnState(),
      filterModel: api.getFilterModel(),
      sortModel:
        typeof api.getSortModel === "function"
          ? api.getSortModel()
          : undefined,
    };
    if (!payload.sortModel) delete payload.sortModel;
    localStorage.setItem(LS_GRID_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

function CustomLegend({ payload, activeCluster, onSelect, counts }) {
  if (!payload?.length) return null;
  const byValue = Object.fromEntries(payload.map((e) => [e.value, e]));
  const entries = CLUSTER_ORDER.map((code) => byValue[code]).filter(Boolean);
  return (
    <div className="scatter-legend-box">
      <div className="scatter-legend-title">Cohort</div>
      <ul className="scatter-legend">
        {entries.map((entry) => {
          const code = entry.value;
          const selected = activeCluster === code;
          const n = counts?.[code] ?? CLUSTER_FALLBACK_COUNTS[code] ?? "?";
          return (
            <li key={code}>
              <button
                type="button"
                className={`scatter-legend-btn${selected ? " is-active" : ""}`}
                style={{ "--cluster-color": entry.color }}
                onClick={() => onSelect(code)}
                title={`Filter grid to ${code}`}
              >
                <span className="scatter-legend-swatch" />
                <span>
                  {code} (n={n})
                </span>
              </button>
            </li>
          );
        })}
        <li>
          <button
            type="button"
            className={`scatter-legend-btn scatter-legend-all${
              activeCluster === "all" ? " is-active" : ""
            }`}
            onClick={() => onSelect("all")}
          >
            All
          </button>
        </li>
      </ul>
    </div>
  );
}

function HullFills({ hullSeries, activeCluster }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale) return null;

  return (
    <g className="scatter-hulls" style={{ pointerEvents: "none" }}>
      {CLUSTER_ORDER.map((code) => {
        const pts = hullSeries[code];
        if (!pts?.length) return null;
        const active = activeCluster === "all" || activeCluster === code;
        const points = pts.map((p) => ({
          x: xScale(p.cltv),
          y: yScale(p.incentive),
        }));
        return (
          <Polygon
            key={`hull-${code}`}
            points={points}
            fill={CLUSTER_COLORS[code]}
            fillOpacity={active ? 0.12 : 0.04}
            stroke={CLUSTER_COLORS[code]}
            strokeWidth={1.2}
            strokeOpacity={active ? 0.9 : 0.25}
          />
        );
      })}
    </g>
  );
}

export default function App() {
  const [pane, setPane] = useState(readNav);
  const [navCollapsed, setNavCollapsed] = useState(readNavCollapsed);
  const [loans, setLoans] = useState([]);
  const [hulls, setHulls] = useState({});
  const [counts, setCounts] = useState(CLUSTER_FALLBACK_COUNTS);
  const [tapeError, setTapeError] = useState(null);
  const [tapeLoading, setTapeLoading] = useState(true);
  const [clusterFilter, setClusterFilter] = useState(readClusterFilter);

  const [asfLoans, setAsfLoans] = useState([]);
  const [asfTotal, setAsfTotal] = useState(0);
  const [asfLoading, setAsfLoading] = useState(false);
  const [asfError, setAsfError] = useState(null);
  const [asfVisible, setAsfVisible] = useState(null);

  const [stratRows, setStratRows] = useState([]);
  const [stratMeta, setStratMeta] = useState(null);
  const [stratLoading, setStratLoading] = useState(false);
  const [stratError, setStratError] = useState(null);
  const [stratMetric, setStratMetric] = useState("upb");
  const [stratCohort, setStratCohort] = useState("all");
  const [stratHasPostal, setStratHasPostal] = useState(false);
  const [stratDrill, setStratDrill] = useState(null);
  const [stratDrillLoans, setStratDrillLoans] = useState([]);
  const [stratDrillTotal, setStratDrillTotal] = useState(0);
  const [stratDrillVisible, setStratDrillVisible] = useState(null);
  const [stratDrillLoading, setStratDrillLoading] = useState(false);
  const [stratDrillError, setStratDrillError] = useState(null);

  const [cohortStats, setCohortStats] = useState([]);
  const [cohortStatsError, setCohortStatsError] = useState(null);

  const [scenarios, setScenarios] = useState([]);
  const [aggregates, setAggregates] = useState([]);
  const [ranScenarioIds, setRanScenarioIds] = useState([]);
  const [runMeta, setRunMeta] = useState(null);
  const [neonNote, setNeonNote] = useState(null);
  const [neonStatus, setNeonStatus] = useState(null);
  const [neonMonth1Rows, setNeonMonth1Rows] = useState([]);
  const [neonMonth1Total, setNeonMonth1Total] = useState(0);
  const [neonCfLoading, setNeonCfLoading] = useState(false);
  const [selectedScenarioId, setSelectedScenarioId] = useState("S05");
  const [selectedLoanId, setSelectedLoanId] = useState(null);
  const [selectedCohort, setSelectedCohort] = useState(null);
  /** agg = scenario aggregates; month1 = all loans for scenario; loanMonth = multi-month. */
  const [cfView, setCfView] = useState("agg");
  const [loanMonthRows, setLoanMonthRows] = useState([]);
  const [loanMonthLoading, setLoanMonthLoading] = useState(false);
  const [runError, setRunError] = useState(null);
  const [running, setRunning] = useState(false);

  const [qcRows, setQcRows] = useState([]);
  const [qcMeta, setQcMeta] = useState(null);
  const [qcLoading, setQcLoading] = useState(false);
  const [qcError, setQcError] = useState(null);
  const [qcStatusFilter, setQcStatusFilter] = useState("all"); // all | pass | fail
  const [qcView, setQcView] = useState("grid"); // grid | chart
  const [qcSelectedRule, setQcSelectedRule] = useState(null);
  const [qcDrillLoans, setQcDrillLoans] = useState([]);
  const [qcDrillTotal, setQcDrillTotal] = useState(0);
  const [qcDrillVisible, setQcDrillVisible] = useState(null);
  const [qcDrillLoading, setQcDrillLoading] = useState(false);
  const [qcDrillError, setQcDrillError] = useState(null);

  const [assumptionRows, setAssumptionRows] = useState([]);
  const [assumptionMeta, setAssumptionMeta] = useState(null);
  const [assumptionLoading, setAssumptionLoading] = useState(false);
  const [assumptionError, setAssumptionError] = useState(null);

  const gridApiRef = useRef(null);
  const restoringRef = useRef(false);
  const saveTimerRef = useRef(null);

  useEffect(() => {
    try {
      localStorage.setItem(LS_NAV_KEY, pane);
    } catch {
      /* ignore */
    }
  }, [pane]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setTapeLoading(true);
      setTapeError(null);
      try {
        const res = await fetch("/cluster-tape.json");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setLoans(Array.isArray(data.loans) ? data.loans : []);
        setHulls(data.hulls || {});
        if (data.meta?.counts) setCounts(data.meta.counts);
      } catch (err) {
        if (!cancelled) {
          setTapeError(err.message || String(err));
          setLoans([]);
        }
      } finally {
        if (!cancelled) setTapeLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ASF Tape loans from Neon (Excel fallback via API).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setAsfLoading(true);
      setAsfError(null);
      try {
        const res = await fetch(apiUrl("/api/asf/tape?limit=2000"));
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        if (cancelled) return;
        setAsfLoans(data.loans || []);
        setAsfTotal(data.total ?? (data.loans || []).length);
      } catch (err) {
        if (!cancelled) {
          setAsfError(err.message || String(err));
          setAsfLoans([]);
        }
      } finally {
        if (!cancelled) setAsfLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Stratification — fetch ALL dimensions so every cut is visible.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStratLoading(true);
      setStratError(null);
      setStratDrill(null);
      setStratDrillLoans([]);
      setStratDrillTotal(0);
      setStratDrillError(null);
      try {
        const cohortQs =
          stratCohort && stratCohort !== "all"
            ? `&cohort=${encodeURIComponent(stratCohort)}`
            : "";
        // Probe state first for KPIs + postal flag, then fetch remaining dims.
        const probeRes = await fetch(
          apiUrl(
            `/api/asf/stratification?by=${encodeURIComponent("state")}${cohortQs}`
          )
        );
        if (!probeRes.ok) {
          const detail = await probeRes.text();
          throw new Error(`State: HTTP ${probeRes.status}: ${detail}`);
        }
        const probe = await probeRes.json();
        const hasPostal = Boolean(probe.has_postal_code);
        if (cancelled) return;
        setStratHasPostal(hasPostal);

        const dims = STRAT_DIMS_BASE.filter(
          (d) => d.id !== "zip3" || hasPostal
        );
        const rest = dims.filter((d) => d.id !== "state");
        const restResults = await Promise.all(
          rest.map(async (dim) => {
            const res = await fetch(
              apiUrl(
                `/api/asf/stratification?by=${encodeURIComponent(dim.id)}${cohortQs}`
              )
            );
            if (!res.ok) {
              const detail = await res.text();
              throw new Error(`${dim.label}: HTTP ${res.status}: ${detail}`);
            }
            const data = await res.json();
            return { dim, data };
          })
        );
        if (cancelled) return;
        const results = [
          { dim: dims.find((d) => d.id === "state"), data: probe },
          ...restResults,
        ];
        const combined = [];
        let tape_row_count = probe.tape_row_count ?? null;
        let tape_upb = probe.tape_upb ?? null;
        let wac = probe.wac ?? null;
        let wam = probe.wam ?? null;
        let seasoned_wac = probe.seasoned_wac ?? null;
        for (const { dim, data } of results) {
          if (!dim) continue;
          if (tape_row_count == null && data.tape_row_count != null) {
            tape_row_count = data.tape_row_count;
          }
          if (tape_upb == null && data.tape_upb != null) {
            tape_upb = data.tape_upb;
          }
          if (wac == null && data.wac != null) wac = data.wac;
          if (wam == null && data.wam != null) wam = data.wam;
          if (seasoned_wac == null && data.seasoned_wac != null) {
            seasoned_wac = data.seasoned_wac;
          }
          if (data.has_postal_code) setStratHasPostal(true);
          for (const row of data.rows || []) {
            combined.push({
              ...row,
              dimension: dim.label,
              dimension_id: dim.id,
              row_key: `${dim.id}::${row.bucket}`,
            });
          }
        }
        setStratRows(combined);
        setStratMeta({
          n_dimensions: dims.length,
          n_buckets: combined.length,
          tape_row_count,
          tape_upb,
          wac,
          wam,
          seasoned_wac,
          has_postal_code: hasPostal,
          cohort: stratCohort,
        });
      } catch (err) {
        if (!cancelled) {
          setStratError(err.message || String(err));
          setStratRows([]);
          setStratMeta(null);
          setStratHasPostal(false);
        }
      } finally {
        if (!cancelled) setStratLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [stratCohort]);

  // Cohort pool stats from Neon asf_tape.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/asf/cohort-stats"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setCohortStats(data.rows || []);
          setCohortStatsError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setCohortStats([]);
          setCohortStatsError(err.message || String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Prefer Neon for scenarios + month-1 CF; fall back to static JSON.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let loadedFromNeon = false;
      try {
        const [neonScenRes, neonStatusRes] = await Promise.all([
          fetch(apiUrl("/api/neon/scenarios")).catch(() => null),
          fetch(apiUrl("/api/neon/status")).catch(() => null),
        ]);
        if (cancelled) return;

        if (neonStatusRes?.ok) {
          const st = await neonStatusRes.json();
          setNeonStatus(st);
          setRanScenarioIds(st.month1_scenario_ids || []);
          setNeonNote(
            `Neon · scenarios=${st.scenarios} · month1=${st.loan_cashflows_month1} · orphans=${st.orphans}`
          );
          loadedFromNeon = true;
        } else if (neonStatusRes && !neonStatusRes.ok) {
          setNeonNote(null);
        }

        if (neonScenRes?.ok) {
          const g = await neonScenRes.json();
          setScenarios(g.scenarios || []);
          loadedFromNeon = true;
        } else {
          const gridRes = await fetch(apiUrl("/api/scenarios/grid")).catch(() => null);
          if (gridRes?.ok) {
            const g = await gridRes.json();
            setScenarios(g.scenarios || []);
          }
        }
      } catch {
        /* offline — panes still usable */
      }

      try {
        const monthRes = await fetch(apiUrl("/api/cashflows/month1")).catch(() => null);
        if (!cancelled && monthRes?.ok) {
          const m = await monthRes.json();
          setAggregates(m.aggregates || []);
          if (m.ran_scenario_ids?.length) {
            setRanScenarioIds(m.ran_scenario_ids);
          }
        } else {
          const staticRes = await fetch("/cohort-month1.json");
          if (!cancelled && staticRes.ok) {
            const m = await staticRes.json();
            setAggregates(m.aggregates || []);
            if (!loadedFromNeon) {
              setRanScenarioIds(
                (m.meta?.ran_scenario_ids || m.aggregates || [])
                  .map((x) => (typeof x === "string" ? x : x.scenario_id))
                  .filter(Boolean)
              );
              if (!scenarios.length && m.aggregates?.length) {
                setScenarios(
                  m.aggregates.map((a) => ({
                    scenario_id: a.scenario_id,
                    cohort: a.cohort,
                    psa_multiple: a.psa_multiple,
                    sda_multiple: a.sda_multiple,
                    recovery_rate: a.recovery_rate,
                    recovery_period_months: a.recovery_period_months,
                    recovery_lag_months: a.recovery_lag_months,
                  }))
                );
              }
            }
          }
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Loan-level month-1 rows from Neon for ALL loans in selected scenario.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!selectedScenarioId || (cfView !== "month1" && pane !== "cashflow")) {
        return;
      }
      if (cfView === "agg" || cfView === "loanMonth") return;
      setNeonCfLoading(true);
      try {
        const res = await fetch(
          apiUrl(
            `/api/neon/cashflows/month1?scenario_id=${encodeURIComponent(
              selectedScenarioId
            )}&limit=5000`
          )
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        let rows = data.rows || [];
        if (selectedLoanId) {
          rows = rows.filter((r) => r.loan_id === selectedLoanId);
        }
        setNeonMonth1Rows(rows);
        setNeonMonth1Total(data.total ?? (data.rows || []).length);
      } catch (err) {
        if (!cancelled) {
          setNeonMonth1Rows([]);
          setNeonMonth1Total(0);
          setNeonNote((prev) =>
            prev?.startsWith("Neon")
              ? `${prev} · month1 fetch failed: ${err.message || err}`
              : `Neon month1 fetch failed: ${err.message || err}`
          );
        }
      } finally {
        if (!cancelled) setNeonCfLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedScenarioId, selectedLoanId, cfView, pane]);

  // Multi-month loan×scenario drill from Neon loan_month_cf_enriched.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (cfView !== "loanMonth" || !selectedLoanId || !selectedScenarioId) {
        setLoanMonthRows([]);
        return;
      }
      setLoanMonthLoading(true);
      try {
        const qs = new URLSearchParams({
          loan_id: selectedLoanId,
          scenario_id: selectedScenarioId,
        });
        const res = await fetch(apiUrl(`/api/neon/cashflows/loan-month?${qs}`));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setLoanMonthRows(data.rows || []);
      } catch {
        if (!cancelled) setLoanMonthRows([]);
      } finally {
        if (!cancelled) setLoanMonthLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cfView, selectedLoanId, selectedScenarioId]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_CLUSTER_KEY, clusterFilter);
    } catch {
      /* ignore */
    }
  }, [clusterFilter]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setQcLoading(true);
      setQcError(null);
      try {
        const res = await fetch(apiUrl("/api/qc/results"));
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        if (cancelled) return;
        setQcRows(Array.isArray(data.results) ? data.results : []);
        setQcMeta({
          tape_row_count: data.tape_row_count,
          run_id: data.run_id,
          n: data.n,
        });
      } catch (err) {
        if (!cancelled) {
          setQcError(err.message || String(err));
          setQcRows([]);
          setQcMeta(null);
        }
      } finally {
        if (!cancelled) setQcLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setAssumptionLoading(true);
      setAssumptionError(null);
      try {
        const res = await fetch(apiUrl("/api/assumptions"));
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        if (cancelled) return;
        setAssumptionRows(
          Array.isArray(data.assumptions) ? data.assumptions : []
        );
        setAssumptionMeta({
          n: data.n,
          source: data.source,
          bootstrap: data.bootstrap,
        });
      } catch (err) {
        if (!cancelled) {
          setAssumptionError(err.message || String(err));
          setAssumptionRows([]);
          setAssumptionMeta(null);
        }
      } finally {
        if (!cancelled) setAssumptionLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const qcActiveRows = useMemo(() => {
    return (qcRows || [])
      .filter((r) => r && r.source !== "demo")
      .filter((r) => r.outcome === "pass" || r.outcome === "fail")
      .map((r) => ({
        ...r,
        rule_name:
          r.rule_name ||
          (r.edit_number != null ? `NQM-${r.edit_number}` : r.check_id),
        status_label:
          r.outcome === "pass" ? "Pass" : r.outcome === "fail" ? "Fail" : "",
      }));
  }, [qcRows]);

  const qcSummary = useMemo(() => {
    const pass = qcActiveRows.filter((r) => r.outcome === "pass").length;
    const fail = qcActiveRows.filter((r) => r.outcome === "fail").length;
    const total = pass + fail;
    const pct = total ? (100 * pass) / total : null;
    return { pass, fail, total, pct };
  }, [qcActiveRows]);

  const qcFilteredRows = useMemo(() => {
    if (qcStatusFilter === "pass") {
      return qcActiveRows.filter((r) => r.outcome === "pass");
    }
    if (qcStatusFilter === "fail") {
      return qcActiveRows.filter((r) => r.outcome === "fail");
    }
    return qcActiveRows;
  }, [qcActiveRows, qcStatusFilter]);

  const qcChartData = useMemo(
    () => [
      { name: "Pass", value: qcSummary.pass, fill: "#1F8A44" },
      { name: "Fail", value: qcSummary.fail, fill: "#C62828" },
    ],
    [qcSummary.pass, qcSummary.fail]
  );

  const asfColumnDefs = useMemo(
    () => [
      {
        field: "loan_id",
        headerName: "Loan Id",
        width: 100,
        pinned: "left",
        lockPinned: true,
        cellClass: "cf-id",
      },
      moneyCol("current_loan_amount", "UPB", 110),
      {
        field: "current_interest_rate",
        headerName: "Interest Rate",
        width: 96,
        valueFormatter: (p) => fmtPct(p.value, 2),
        cellClass: "cf-num",
      },
      intCol("original_fico", "FICO", 72),
      {
        field: "original_ltv",
        headerName: "LTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "original_cltv",
        headerName: "CLTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      { field: "state", headerName: "State", width: 64 },
      {
        field: "documentation_type",
        headerName: "Documentation Type",
        flex: 1.2,
        minWidth: 140,
      },
      { field: "property_type", headerName: "Property Type", width: 110 },
      { field: "occupancy", headerName: "Occupancy", width: 100 },
      { field: "loan_purpose", headerName: "Loan Purpose", width: 110 },
      intCol("remaining_term", "Remaining Term", 120),
      {
        field: "refinance_incentive",
        headerName: "Refinance Incentive",
        width: 130,
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
      { field: "cohort", headerName: "Cohort", flex: 1.4, minWidth: 160 },
      {
        field: "has_mi",
        headerName: "Mortgage Insurance",
        headerTooltip: "Mortgage Insurance (private MI on the loan)",
        width: 140,
        cellClass: "cf-num",
        valueFormatter: (p) => {
          if (p.value === true || p.value === "true" || p.value === 1) return "Yes";
          if (p.value === false || p.value === "false" || p.value === 0) return "No";
          return "";
        },
        filterValueGetter: (p) => {
          const v = p.data?.has_mi;
          if (v === true || v === "true" || v === 1) return "Yes";
          if (v === false || v === "false" || v === 0) return "No";
          return "";
        },
      },
    ],
    []
  );

  const asfToolbarStart = useMemo(() => {
    const total = asfTotal || asfLoans.length || 0;
    const shown =
      asfVisible != null ? asfVisible : asfLoading ? null : asfLoans.length;
    return (
      <p className="asf-grid-summary" aria-live="polite">
        <span className="asf-grid-summary-total">
          {total.toLocaleString()} {total === 1 ? "Loan" : "Loans"}
        </span>
        {shown != null ? (
          <span
            className={
              shown !== total
                ? "asf-grid-summary-filter is-filtered"
                : "asf-grid-summary-filter"
            }
          >
            {" · "}
            {shown.toLocaleString()} Shown
          </span>
        ) : null}
      </p>
    );
  }, [asfTotal, asfLoans.length, asfVisible, asfLoading]);

  const onAsfRowStats = useCallback((stats) => {
    if (stats?.visible != null) setAsfVisible(stats.visible);
  }, []);

  const assumptionColumnDefs = useMemo(
    () => [
      {
        field: "assumption_id",
        headerName: "ID",
        hide: true,
      },
      { field: "category", headerName: "Category", width: 120 },
      { field: "name", headerName: "Name", width: 180 },
      {
        field: "value",
        headerName: "Value",
        flex: 1.4,
        minWidth: 160,
        wrapText: true,
        autoHeight: true,
      },
      { field: "unit", headerName: "Unit", width: 88 },
      {
        field: "applies_to",
        headerName: "Applies To",
        flex: 1,
        minWidth: 140,
      },
      {
        field: "related_data_path",
        headerName: "Data Path",
        flex: 1.1,
        minWidth: 160,
      },
      {
        field: "source_name",
        headerName: "Source",
        flex: 1.2,
        minWidth: 160,
      },
      {
        field: "source_url",
        headerName: "Source URL",
        flex: 1.4,
        minWidth: 180,
        cellRenderer: (p) => {
          const url = p.value;
          if (!url) return "";
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              style={{ color: "#0B4F9C" }}
            >
              {url}
            </a>
          );
        },
      },
      {
        field: "notes",
        headerName: "Notes",
        flex: 1.6,
        minWidth: 200,
        wrapText: true,
        autoHeight: true,
      },
    ],
    []
  );

  const qcColumnDefs = useMemo(
    () => [
      {
        field: "nl_description",
        headerName: "Description",
        flex: 2,
        minWidth: 220,
        pinned: "left",
        lockPinned: true,
      },
      {
        field: "status_label",
        headerName: "Status",
        width: 80,
        cellClass: (p) => {
          if (p.value === "Pass") return "qc-outcome-pass";
          if (p.value === "Fail") return "qc-outcome-fail";
          return "";
        },
      },
      {
        field: "pass_count",
        headerName: "Passed Loans",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
      {
        field: "fail_count",
        headerName: "Failed Loans",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
    ],
    []
  );

  const qcDrillColumnDefs = useMemo(
    () => [
      {
        field: "loan_id",
        headerName: "Loan Id",
        width: 100,
        pinned: "left",
        lockPinned: true,
        cellClass: "cf-id",
      },
      moneyCol("current_loan_amount", "UPB", 110),
      {
        field: "current_interest_rate",
        headerName: "Interest Rate",
        width: 96,
        valueFormatter: (p) => fmtPct(p.value, 2),
        cellClass: "cf-num",
      },
      intCol("original_fico", "FICO", 72),
      {
        field: "original_ltv",
        headerName: "LTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "original_cltv",
        headerName: "CLTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      { field: "state", headerName: "State", width: 64 },
      { field: "postal_code", headerName: "Postal Code", width: 96 },
      {
        field: "documentation_type",
        headerName: "Documentation Type",
        flex: 1.2,
        minWidth: 140,
      },
      { field: "property_type", headerName: "Property Type", width: 110 },
      { field: "occupancy", headerName: "Occupancy", width: 100 },
      { field: "loan_purpose", headerName: "Loan Purpose", width: 110 },
      { field: "cohort", headerName: "Cohort", flex: 1.2, minWidth: 140 },
    ],
    []
  );

  const loadQcDrillLoans = useCallback(async (rule) => {
    if (!rule?.check_id) {
      setQcSelectedRule(null);
      setQcDrillLoans([]);
      setQcDrillTotal(0);
      setQcDrillError(null);
      return;
    }
    setQcSelectedRule(rule);
    setQcDrillLoading(true);
    setQcDrillError(null);
    setQcDrillVisible(null);
    try {
      const res = await fetch(
        apiUrl(
          `/api/qc/results/${encodeURIComponent(rule.check_id)}/loans?failing_only=true&limit=2000`
        )
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      setQcDrillLoans(Array.isArray(data.loans) ? data.loans : []);
      setQcDrillTotal(data.total ?? (data.loans || []).length);
    } catch (err) {
      setQcDrillError(err.message || String(err));
      setQcDrillLoans([]);
      setQcDrillTotal(0);
    } finally {
      setQcDrillLoading(false);
    }
  }, []);

  const onQcRuleDrill = useCallback(
    (row) => {
      if (!row?.check_id) return;
      loadQcDrillLoans(row);
    },
    [loadQcDrillLoans]
  );

  const onQcDrillRowStats = useCallback((stats) => {
    if (stats?.visible != null) setQcDrillVisible(stats.visible);
  }, []);

  const qcDrillToolbarStart = useMemo(() => {
    if (!qcSelectedRule) return null;
    const total = qcDrillTotal || qcDrillLoans.length || 0;
    const shown =
      qcDrillVisible != null
        ? qcDrillVisible
        : qcDrillLoading
          ? null
          : qcDrillLoans.length;
    return (
      <p className="asf-grid-summary" aria-live="polite">
        <span className="asf-grid-summary-total">
          {qcSelectedRule.rule_name}
          {" · "}
          {total.toLocaleString()} {total === 1 ? "Loan" : "Loans"}
        </span>
        {shown != null ? (
          <span
            className={
              shown !== total
                ? "asf-grid-summary-filter is-filtered"
                : "asf-grid-summary-filter"
            }
          >
            {" · "}
            {shown.toLocaleString()} Shown
          </span>
        ) : null}
      </p>
    );
  }, [
    qcSelectedRule,
    qcDrillTotal,
    qcDrillLoans.length,
    qcDrillVisible,
    qcDrillLoading,
  ]);

  const stratDims = useMemo(
    () =>
      STRAT_DIMS_BASE.filter(
        (d) => d.id !== "zip3" || stratHasPostal || stratMeta?.has_postal_code
      ),
    [stratHasPostal, stratMeta?.has_postal_code]
  );

  const stratByDim = useMemo(() => {
    const map = {};
    for (const dim of stratDims) map[dim.id] = [];
    for (const row of stratRows) {
      if (!map[row.dimension_id]) map[row.dimension_id] = [];
      map[row.dimension_id].push(row);
    }
    return map;
  }, [stratRows, stratDims]);

  const loadStratDrillLoans = useCallback(
    async (dimId, bucket) => {
      const dim = STRAT_DIMS_BASE.find((d) => d.id === dimId);
      if (!dimId || bucket == null || bucket === "") {
        setStratDrill(null);
        setStratDrillLoans([]);
        setStratDrillTotal(0);
        setStratDrillError(null);
        return;
      }
      setStratDrill({
        dimension: dimId,
        label: dim?.label || dimId,
        bucket: String(bucket),
      });
      setStratDrillLoading(true);
      setStratDrillError(null);
      setStratDrillVisible(null);
      try {
        const qs = new URLSearchParams({
          by: dimId,
          bucket: String(bucket),
          limit: "2000",
        });
        if (stratCohort && stratCohort !== "all") {
          qs.set("cohort", stratCohort);
        }
        const res = await fetch(
          apiUrl(`/api/asf/stratification/loans?${qs.toString()}`)
        );
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        setStratDrillLoans(Array.isArray(data.loans) ? data.loans : []);
        setStratDrillTotal(data.total ?? (data.loans || []).length);
      } catch (err) {
        setStratDrillError(err.message || String(err));
        setStratDrillLoans([]);
        setStratDrillTotal(0);
      } finally {
        setStratDrillLoading(false);
      }
    },
    [stratCohort]
  );

  const onStratBucketClick = useCallback(
    (dimId, bucket) => {
      loadStratDrillLoans(dimId, bucket);
    },
    [loadStratDrillLoans]
  );

  const onStratDrillRowStats = useCallback((stats) => {
    if (stats?.visible != null) setStratDrillVisible(stats.visible);
  }, []);

  const clearStratDrill = useCallback(() => {
    setStratDrill(null);
    setStratDrillLoans([]);
    setStratDrillTotal(0);
    setStratDrillError(null);
    setStratDrillVisible(null);
  }, []);

  const stratDrillToolbarStart = useMemo(() => {
    if (!stratDrill) return null;
    const total = stratDrillTotal || stratDrillLoans.length || 0;
    const shown =
      stratDrillVisible != null
        ? stratDrillVisible
        : stratDrillLoading
          ? null
          : stratDrillLoans.length;
    return (
      <p className="asf-grid-summary" aria-live="polite">
        <span className="asf-grid-summary-total">
          {stratDrill.label}: {stratDrill.bucket}
          {" · "}
          {total.toLocaleString()} {total === 1 ? "Loan" : "Loans"}
        </span>
        {shown != null ? (
          <span
            className={
              shown !== total
                ? "asf-grid-summary-filter is-filtered"
                : "asf-grid-summary-filter"
            }
          >
            {" · "}
            {shown.toLocaleString()} Shown
          </span>
        ) : null}
        <button
          type="button"
          className="linkish strat-drill-clear"
          onClick={clearStratDrill}
        >
          Clear Drill
        </button>
      </p>
    );
  }, [
    stratDrill,
    stratDrillTotal,
    stratDrillLoans.length,
    stratDrillVisible,
    stratDrillLoading,
    clearStratDrill,
  ]);

  const exportStratCsv = useCallback(() => {
    const headers = [
      "dimension",
      "bucket",
      "loan_count",
      "upb",
      "avg_ltv",
      "avg_cltv",
      "avg_fico",
      "avg_rate",
      "wac",
      "avg_refi_incentive",
    ];
    const lines = [headers.join(",")];
    for (const row of stratRows) {
      lines.push(
        headers
          .map((h) => {
            const v = row[h];
            if (v == null) return "";
            const s = String(v);
            return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
          })
          .join(",")
      );
    }
    const blob = new Blob([lines.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "stratification.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [stratRows]);

  const copyStratRows = useCallback(async () => {
    const headers = [
      "dimension",
      "bucket",
      "loan_count",
      "upb",
      "avg_ltv",
      "avg_cltv",
      "avg_fico",
      "avg_rate",
      "wac",
      "avg_refi_incentive",
    ];
    const lines = [headers.join("\t")];
    for (const row of stratRows) {
      lines.push(headers.map((h) => (row[h] == null ? "" : String(row[h]))).join("\t"));
    }
    const tsv = lines.join("\n");
    try {
      await navigator.clipboard.writeText(tsv);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = tsv;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  }, [stratRows]);

  const cohortStatsColumnDefs = useMemo(
    () => [
      { field: "cohort", headerName: "Cohort", flex: 1.8, minWidth: 200 },
      intCol("loan_count", "Loans", 80),
      moneyCol("upb", "UPB", 120),
      {
        field: "avg_ltv",
        headerName: "Avg LTV",
        width: 88,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "avg_cltv",
        headerName: "Avg CLTV",
        width: 88,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "avg_fico",
        headerName: "Avg FICO",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 0),
        cellClass: "cf-num",
      },
      {
        field: "avg_rate",
        headerName: "Avg Rate",
        width: 88,
        valueFormatter: (p) => fmtPct(p.value, 2),
        cellClass: "cf-num",
      },
      {
        field: "avg_refi_incentive",
        headerName: "Avg Refi",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
      {
        field: "avg_remaining_term",
        headerName: "Avg Rem",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 0),
        cellClass: "cf-num",
      },
    ],
    []
  );

  const loanColumnDefs = useMemo(
    () => [
      {
        field: "loanId",
        headerName: "Loan ID",
        flex: 1.1,
        minWidth: 100,
        cellClass: "cf-id",
      },
      intCol("fico", "FICO", 72),
      {
        field: "cltv",
        headerName: "CLTV",
        width: 90,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "documentation",
        headerName: "Documentation",
        flex: 1.2,
        minWidth: 120,
      },
      intCol("remainingTerm", "Remaining Term", 110),
      {
        field: "refinanceIncentive",
        headerName: "Refi Incentive",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
      {
        field: "cluster",
        headerName: "Cohort",
        flex: 1.6,
        minWidth: 180,
      },
    ],
    []
  );

  const scenarioColumnDefs = useMemo(
    () => [
      {
        field: "_scenarioLabel",
        headerName: "Scenario",
        width: 140,
        sortable: false,
        filter: false,
        rowSpan: (p) => Math.max(1, p.data?._scenarioSpan || 1),
        cellClassRules: {
          "cf-id": () => true,
          "cf-row-span": (p) => (p.data?._scenarioSpan || 0) > 1,
        },
        valueGetter: (p) =>
          p.data?._scenarioSpan === 0 ? "" : p.data?._scenarioLabel || "",
      },
      { field: "scenario_id", headerName: "ID", hide: true },
      { field: "cohort", headerName: "Cohort", flex: 1.8, minWidth: 180 },
      {
        field: "pca_level",
        headerName: "PCA",
        width: 70,
        valueGetter: (p) => pcaLabel(p.data),
      },
      {
        field: "sta_level",
        headerName: "STA",
        width: 70,
        valueGetter: (p) => staLabel(p.data),
      },
      intCol("psa_multiple", "PSA", 64),
      intCol("sda_multiple", "SDA", 64),
      {
        field: "recovery_rate",
        headerName: "Rec %",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 0),
        cellClass: "cf-num",
      },
      intCol("recovery_period_months", "Rec Mos", 80),
      intCol("recovery_lag_months", "Lag Fallback", 96),
      intCol("avg_used_recovery_lag_months", "Avg Used Lag", 100),
      {
        field: "ran",
        headerName: "Ran",
        width: 64,
        valueGetter: (p) =>
          ranScenarioIds.includes(p.data.scenario_id) ? "Y" : "",
      },
    ],
    [ranScenarioIds]
  );

  const aggColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", hide: true },
      { field: "cohort", headerName: "Cohort", flex: 1.6, minWidth: 180 },
      {
        field: "pca_level",
        headerName: "PCA",
        width: 64,
        valueGetter: (p) => pcaLabel(p.data),
      },
      {
        field: "sta_level",
        headerName: "STA",
        width: 64,
        valueGetter: (p) => staLabel(p.data),
      },
      intCol("n_loans", "Loans", 72),
      moneyCol("beginning_balance", "Begin Bal", 110),
      moneyCol("interest", "Interest", 100),
      moneyCol("scheduled_principal", "Sched Prin", 100),
      moneyCol("default_amt", "New Default", 100),
      moneyCol("default", "New Default", 100),
      moneyCol("new_default", "New Default", 100),
      moneyCol("prepay", "Prepay", 90),
      moneyCol("liquidated_default", "Liq Default", 100),
      moneyCol("recovery", "Recovery", 90),
      moneyCol("realized_loss", "Realized Loss", 100),
      moneyCol("total_cash", "Total Cash", 100),
      moneyCol("ending_balance", "End UPB", 110),
      intCol("avg_used_recovery_lag_months", "Avg Used Lag", 100),
    ],
    []
  );

  const cfMonth1ColumnDefs = useMemo(
    () => [
      { field: "loan_id", headerName: "Loan", width: 100, cellClass: "cf-id" },
      { field: "scenario_id", headerName: "ID", hide: true },
      { field: "cohort", headerName: "Cohort", flex: 1.4, minWidth: 160 },
      {
        field: "pca_level",
        headerName: "PCA",
        width: 64,
        valueGetter: (p) => pcaLabel(p.data),
      },
      {
        field: "sta_level",
        headerName: "STA",
        width: 64,
        valueGetter: (p) => staLabel(p.data),
      },
      intCol("used_recovery_lag_months", "Used Lag", 80),
      {
        headerName: "1 · Performing UPB",
        children: [
          intCol("month", "Mo", 56),
          moneyCol("beginning_balance", "Beg UPB", 110),
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched Prin", 100),
          {
            field: "cpr",
            headerName: "CPR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 2),
            cellClass: "cf-num",
          },
          {
            field: "cdr",
            headerName: "CDR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 3),
            cellClass: "cf-num",
          },
          moneyCol("prepay", "Prepay", 90),
          moneyCol("new_default", "New Default", 100),
          moneyCol("default_amt", "New Default", 100),
          moneyCol("ending_balance", "End UPB", 110),
        ],
      },
      {
        headerName: "2 · Default Roll",
        children: [
          moneyCol("beginning_default_balance", "Beg Def Bal", 110),
          moneyCol("liquidated_default", "Liq Default", 100),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("realized_loss", "Realized Loss", 100),
          moneyCol("ending_default_balance", "End Def Bal", 110),
        ],
      },
      {
        headerName: "3 · Actual Cash (Defaults ≠ Cash)",
        children: [
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched Prin", 100),
          moneyCol("prepay", "Prepay", 90),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("total_cash", "Total Cash", 100),
        ],
      },
    ],
    []
  );

  const loanMonthColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", hide: true },
      { field: "loan_id", headerName: "Loan", width: 100, cellClass: "cf-id" },
      intCol("used_recovery_lag_months", "Used Lag", 80),
      {
        field: "recovery_rate",
        headerName: "Rec %",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 0),
        cellClass: "cf-num",
      },
      {
        headerName: "1 · Performing UPB",
        children: [
          intCol("month", "Mo", 56),
          moneyCol("beginning_balance", "Beg UPB", 110),
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched Prin", 100),
          {
            field: "cpr",
            headerName: "CPR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 2),
            cellClass: "cf-num",
          },
          {
            field: "cdr",
            headerName: "CDR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 3),
            cellClass: "cf-num",
          },
          moneyCol("prepay", "Prepay", 90),
          moneyCol("new_default", "New Default", 100),
          moneyCol("default_amt", "New Default", 100),
          moneyCol("ending_balance", "End UPB", 110),
        ],
      },
      {
        headerName: "2 · Default Roll",
        children: [
          moneyCol("beginning_default_balance", "Beg Def Bal", 110),
          moneyCol("liquidated_default", "Liq Default", 100),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("realized_loss", "Realized Loss", 100),
          moneyCol("loss", "Loss", 90),
          moneyCol("ending_default_balance", "End Def Bal", 110),
        ],
      },
      {
        headerName: "3 · Actual Cash (Defaults ≠ Cash)",
        children: [
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched Prin", 100),
          moneyCol("prepay", "Prepay", 90),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("total_cash", "Total Cash", 100),
        ],
      },
      {
        field: "pca_level",
        headerName: "PCA",
        width: 64,
        valueGetter: (p) => pcaLabel(p.data),
      },
      {
        field: "sta_level",
        headerName: "STA",
        width: 64,
        valueGetter: (p) => staLabel(p.data),
      },
    ],
    []
  );

  const filteredScenarios = useMemo(() => {
    const base = scenarios.length
      ? scenarios
      : aggregates.map((a) => ({
          scenario_id: a.scenario_id,
          cohort: a.cohort,
          psa_multiple: a.psa_multiple,
          sda_multiple: a.sda_multiple,
          pca_level: a.pca_level,
          sta_level: a.sta_level,
          recovery_rate: a.recovery_rate,
          recovery_period_months: a.recovery_period_months,
          recovery_lag_months: a.recovery_lag_months,
        }));
    const filtered = selectedCohort
      ? base.filter((s) => s.cohort === selectedCohort)
      : base;
    return withScenarioRowSpans(filtered);
  }, [scenarios, aggregates, selectedCohort]);

  const filteredLoans = useMemo(() => {
    if (clusterFilter === "all") return loans;
    return loans.filter((r) => r.cluster === clusterFilter);
  }, [loans, clusterFilter]);

  const scatterByCluster = useMemo(() => {
    const groups = Object.fromEntries(CLUSTER_ORDER.map((c) => [c, []]));
    for (const loan of loans) {
      if (!groups[loan.cluster]) continue;
      if (loan.cltv == null || loan.refinanceIncentive == null) continue;
      groups[loan.cluster].push({
        cltv: loan.cltv,
        incentive: loan.refinanceIncentive,
        loanId: loan.loanId,
        cluster: loan.cluster,
      });
    }
    return groups;
  }, [loans]);

  const hullSeries = useMemo(() => {
    const out = {};
    for (const code of CLUSTER_ORDER) {
      const pts = hulls[code];
      if (!Array.isArray(pts) || pts.length < 3) continue;
      const ring = pts.map((p) => ({
        cltv: p.cltv,
        incentive: p.incentive,
      }));
      const first = ring[0];
      const last = ring[ring.length - 1];
      if (
        first &&
        last &&
        (first.cltv !== last.cltv || first.incentive !== last.incentive)
      ) {
        ring.push({ ...first });
      }
      out[code] = ring;
    }
    return out;
  }, [hulls]);

  const scheduleSave = useCallback(() => {
    if (restoringRef.current) return;
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveGridState(gridApiRef.current);
    }, 200);
  }, []);

  const onGridReady = useCallback((params) => {
    gridApiRef.current = params.api;
    const saved = readGridState();
    if (saved?.columnState?.length) {
      restoringRef.current = true;
      params.api.applyColumnState({
        state: saved.columnState,
        applyOrder: true,
      });
      if (saved.filterModel) {
        params.api.setFilterModel(saved.filterModel);
      }
      if (saved.sortModel && typeof params.api.setSortModel === "function") {
        params.api.setSortModel(saved.sortModel);
      }
      requestAnimationFrame(() => {
        restoringRef.current = false;
      });
    }
  }, []);

  const selectCluster = useCallback((code) => {
    setClusterFilter((prev) => {
      if (code === "all") return "all";
      return prev === code ? "all" : code;
    });
  }, []);

  const selectPane = useCallback((id) => {
    setPane(id);
    if (isNarrowViewport()) {
      setNavCollapsed(true);
    }
  }, []);

  const drillLoan = useCallback((row) => {
    const loanId = row.loanId || row.loan_id;
    const cohort = row.cluster || row.cohort || null;
    setSelectedLoanId(loanId || null);
    setSelectedCohort(cohort);
    if (cohort) setClusterFilter(cohort);
    setCfView("month1");
    setPane("scenarios");
  }, []);

  const drillScenario = useCallback((row) => {
    if (!row?.scenario_id) return;
    setSelectedScenarioId(row.scenario_id);
    if (row.cohort) setSelectedCohort(row.cohort);
    setSelectedLoanId(null);
    setCfView("month1");
    setPane("cashflow");
  }, []);

  const drillAggScenario = useCallback((row) => {
    if (!row?.scenario_id) return;
    setSelectedScenarioId(row.scenario_id);
    if (row.cohort) setSelectedCohort(row.cohort);
    setSelectedLoanId(null);
    setCfView("month1");
  }, []);

  const drillMonth1Loan = useCallback((row) => {
    if (!row?.loan_id || !row?.scenario_id) return;
    setSelectedLoanId(row.loan_id);
    setSelectedScenarioId(row.scenario_id);
    if (row.cohort) setSelectedCohort(row.cohort);
    setCfView("loanMonth");
  }, []);

  const onDrillJump = useCallback((crumb) => {
    if (crumb.id === "loans") {
      setSelectedLoanId(null);
      setSelectedCohort(null);
      setCfView("agg");
      setPane("cohort");
      return;
    }
    if (crumb.id === "scenarios") {
      setCfView("agg");
      setSelectedLoanId(null);
      setPane("scenarios");
      return;
    }
    if (crumb.id === "agg") {
      setCfView("agg");
      setSelectedLoanId(null);
      setPane("cashflow");
      return;
    }
    if (crumb.id === "month1") {
      setCfView("month1");
      setSelectedLoanId(null);
      setPane("cashflow");
    }
  }, []);

  const clearDrill = useCallback(() => {
    setSelectedLoanId(null);
    setSelectedCohort(null);
    setCfView("agg");
  }, []);

  const drillCrumbs = useMemo(() => {
    const crumbs = [{ id: "loans", label: "Cohorts", jumpable: true }];
    if (selectedCohort) {
      crumbs.push({
        id: "cohort",
        label: selectedCohort,
        jumpable: false,
      });
    }
    crumbs.push({ id: "scenarios", label: "Scenarios", jumpable: true });
    crumbs.push({ id: "agg", label: "CF Aggregates", jumpable: cfView !== "agg" });
    if (selectedScenarioId && cfView !== "agg") {
      crumbs.push({
        id: "scenario",
        label: selectedScenarioId,
        jumpable: false,
      });
    }
    if (cfView === "month1" || cfView === "loanMonth") {
      crumbs.push({
        id: "month1",
        label: "All Loans · Month 1",
        jumpable: cfView === "loanMonth",
      });
    }
    if (cfView === "loanMonth" && selectedLoanId) {
      crumbs.push({
        id: "loanMonth",
        label: `${selectedLoanId} · months`,
        jumpable: false,
      });
    } else if (selectedLoanId) {
      crumbs.push({
        id: "loanFilter",
        label: selectedLoanId,
        jumpable: false,
      });
    }
    return crumbs;
  }, [selectedCohort, selectedScenarioId, selectedLoanId, cfView]);

  async function handleRunMonth1() {
    setRunning(true);
    setRunError(null);
    try {
      const res = await fetch(apiUrl("/api/cashflows/run-month1"), {
        method: "POST",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      setAggregates(data.aggregates || []);
      setRanScenarioIds(data.ran_scenario_ids || []);
      setRunMeta(data.parallelism || null);
      setNeonNote(
        data.neon_missing
          ? "DATABASE_URL not set — loan-level CF persisted locally under data/"
          : data.cached
            ? `Loaded ${data.storage?.neon || data.storage?.json || "cache"} · loan-level on Neon`
            : data.storage?.neon || "Run complete · loan-level persisted"
      );
      if (data.aggregates?.length && !scenarios.length) {
        setScenarios(
          data.aggregates.map((a) => ({
            scenario_id: a.scenario_id,
            cohort: a.cohort,
            psa_multiple: a.psa_multiple,
            sda_multiple: a.sda_multiple,
            recovery_rate: a.recovery_rate,
            recovery_period_months: a.recovery_period_months,
            recovery_lag_months: a.recovery_lag_months,
          }))
        );
      }
      setCfView("agg");
      setPane("cashflow");
    } catch (err) {
      setRunError(err.message || String(err));
    } finally {
      setRunning(false);
    }
  }

  const axisTick = {
    fill: "#4A5F7A",
    fontSize: 10,
    fontFamily: FONT,
  };

  const filterLabel =
    clusterFilter === "all" ? "All Cohorts" : clusterFilter;

  const scenarioOptions = useMemo(() => {
    const ids = (
      scenarios.length
        ? scenarios
        : aggregates.map((a) => ({
            scenario_id: a.scenario_id,
            cohort: a.cohort,
          }))
    ).map((s) => ({
      id: s.scenario_id,
      label: `${s.scenario_id}${s.cohort ? ` · ${s.cohort}` : ""}`,
    }));
    return ids;
  }, [scenarios, aggregates]);

  const toggleNav = useCallback(() => {
    setNavCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(LS_NAV_COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <button
            type="button"
            className="nav-toggle"
            onClick={toggleNav}
            title={navCollapsed ? "Open Menu" : "Close Menu"}
            aria-label={navCollapsed ? "Open Menu" : "Close Menu"}
            aria-expanded={!navCollapsed}
            aria-controls="primary-nav"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
              focusable="false"
            >
              {navCollapsed ? (
                <>
                  <path
                    d="M2.5 4.25h11"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                  <path
                    d="M2.5 8h11"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                  <path
                    d="M2.5 11.75h11"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </>
              ) : (
                <path
                  d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              )}
            </svg>
          </button>
          <div className="topbar-brand">
            <img
              className="topbar-mark"
              src="/favicon.svg"
              alt=""
              width={16}
              height={16}
            />
            <span className="topbar-name">CashFlow</span>
            <span className="topbar-version">v0.3.0</span>
            <span className="topbar-page" aria-live="polite">
              {NAV.find((n) => n.id === pane)?.label || ""}
            </span>
          </div>
        </div>
      </header>

      <div className={`shell${navCollapsed ? "" : " nav-open"}`}>
        {!navCollapsed && (
          <button
            type="button"
            className="nav-backdrop"
            aria-label="Close Navigation"
            onClick={() => {
              setNavCollapsed(true);
              try {
                localStorage.setItem(LS_NAV_COLLAPSE_KEY, "1");
              } catch {
                /* ignore */
              }
            }}
          />
        )}
        <nav
          id="primary-nav"
          className={`sidenav${navCollapsed ? " is-collapsed" : ""}`}
          aria-label="Primary Navigation"
        >
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`sidenav-btn${pane === item.id ? " is-active" : ""}`}
              onClick={() => selectPane(item.id)}
              title={item.label}
              aria-label={item.label}
            >
              <span className="sidenav-label-full">{item.label}</span>
              <span className="sidenav-label-short" aria-hidden="true">
                {NAV_SHORT[item.id] || item.label.slice(0, 3)}
              </span>
            </button>
          ))}
        </nav>

        <main className="main">
          {pane === "asf" && (
            <section className="section section-fill section-asf">
              {asfLoading ? (
                <p className="muted">Loading Investor Tape…</p>
              ) : asfError ? (
                <StatusBanner tone="error">Investor Tape: {asfError}</StatusBanner>
              ) : (
                <DataGrid
                  rowData={asfLoans}
                  columnDefs={asfColumnDefs}
                  getRowId={(p) => String(p.data.loan_id)}
                  onRowDrill={drillLoan}
                  onRowStats={onAsfRowStats}
                  toolbarStart={asfToolbarStart}
                  heightClass="grid-wrap-fill"
                  exportName="asf-tape"
                />
              )}
            </section>
          )}

          {pane === "qc" && (
            <section className="section section-fill section-qc">
              <div className="qc-toolbar">
                <div className="qc-kpi-strip" role="toolbar" aria-label="QC Filters">
                  <button
                    type="button"
                    className={`qc-kpi${qcStatusFilter === "all" ? " is-active" : ""}`}
                    onClick={() => setQcStatusFilter("all")}
                  >
                    <span className="qc-kpi-label">Total Rules</span>
                    <span className="qc-kpi-value">{qcSummary.total}</span>
                  </button>
                  <button
                    type="button"
                    className={`qc-kpi qc-kpi-pass${qcStatusFilter === "pass" ? " is-active" : ""}`}
                    onClick={() => setQcStatusFilter("pass")}
                  >
                    <span className="qc-kpi-label">Passed</span>
                    <span className="qc-kpi-value">{qcSummary.pass}</span>
                  </button>
                  <button
                    type="button"
                    className={`qc-kpi qc-kpi-fail${qcStatusFilter === "fail" ? " is-active" : ""}`}
                    onClick={() => setQcStatusFilter("fail")}
                  >
                    <span className="qc-kpi-label">Failed</span>
                    <span className="qc-kpi-value">{qcSummary.fail}</span>
                  </button>
                </div>
                <div
                  className="cf-grid-toolbar-actions qc-view-toggle"
                  role="toolbar"
                  aria-label="QC View"
                >
                  <button
                    type="button"
                    className={`linkish${qcView === "grid" ? " is-active" : ""}`}
                    onClick={() => setQcView("grid")}
                  >
                    Grid
                  </button>
                  <button
                    type="button"
                    className={`linkish${qcView === "chart" ? " is-active" : ""}`}
                    onClick={() => setQcView("chart")}
                  >
                    Chart
                  </button>
                </div>
              </div>

              {qcLoading ? (
                <p className="muted">Loading Loan QC…</p>
              ) : qcError ? (
                <StatusBanner tone="error">Loan QC: {qcError}</StatusBanner>
              ) : !qcActiveRows.length ? (
                <p className="muted">
                  No QC results yet. Load Investor Tape and run QC against Neon.
                </p>
              ) : qcView === "chart" ? (
                <div className="qc-chart-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={qcChartData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={48}
                        outerRadius={80}
                        paddingAngle={2}
                      >
                        {qcChartData.map((entry) => (
                          <Cell key={entry.name} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend verticalAlign="bottom" height={28} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <DataGrid
                  rowData={qcFilteredRows}
                  columnDefs={qcColumnDefs}
                  getRowId={(p) => String(p.data.check_id)}
                  onRowDrill={onQcRuleDrill}
                  heightClass={
                    qcSelectedRule ? "grid-wrap-qc-rules" : "grid-wrap-fill"
                  }
                  exportName="loan-qc"
                />
              )}

              {qcSelectedRule && qcView === "grid" && (
                <div className="qc-drill">
                  {qcDrillLoading ? (
                    <p className="muted">Loading Failed Loans…</p>
                  ) : qcDrillError ? (
                    <StatusBanner tone="error">
                      Failed Loans: {qcDrillError}
                    </StatusBanner>
                  ) : (
                    <DataGrid
                      rowData={qcDrillLoans}
                      columnDefs={qcDrillColumnDefs}
                      getRowId={(p) => String(p.data.loan_id)}
                      onRowDrill={drillLoan}
                      onRowStats={onQcDrillRowStats}
                      toolbarStart={qcDrillToolbarStart}
                      heightClass="grid-wrap-qc-drill"
                      exportName={`qc-${qcSelectedRule.check_id}-loans`}
                    />
                  )}
                </div>
              )}
            </section>
          )}

          {pane === "strat" && (
            <section className="section section-fill section-strat">
              <div className="qc-toolbar strat-topbar">
                <div className="qc-kpi-strip" role="toolbar" aria-label="Stratification KPIs">
                  <div className="qc-kpi is-active" aria-label="Total Loans">
                    <span className="qc-kpi-label">Total Loans</span>
                    <span className="qc-kpi-value">
                      {stratMeta?.tape_row_count != null
                        ? Number(stratMeta.tape_row_count).toLocaleString()
                        : "—"}
                    </span>
                  </div>
                  <div className="qc-kpi" aria-label="UPB">
                    <span className="qc-kpi-label">UPB</span>
                    <span className="qc-kpi-value">
                      {stratMeta?.tape_upb != null
                        ? fmtUpbShort(stratMeta.tape_upb)
                        : "—"}
                    </span>
                  </div>
                  <div className="qc-kpi" aria-label="WAC" title="Weighted Average Coupon">
                    <span className="qc-kpi-label">WAC</span>
                    <span className="qc-kpi-value">
                      {stratMeta?.wac != null
                        ? `${(Number(stratMeta.wac) * 100).toFixed(2)}%`
                        : "—"}
                    </span>
                  </div>
                  <div className="qc-kpi" aria-label="WAM" title="Weighted Average Maturity (Months)">
                    <span className="qc-kpi-label">WAM</span>
                    <span className="qc-kpi-value">
                      {stratMeta?.wam != null
                        ? `${Number(stratMeta.wam).toFixed(0)} Mo`
                        : "—"}
                    </span>
                  </div>
                  <div
                    className="qc-kpi"
                    aria-label="Seasoned WAC"
                    title="UPB-Weighted Rate For Loans Aged 12+ Months (Seasoned Proxy; Dying WAC Not On Tape)"
                  >
                    <span className="qc-kpi-label">Seasoned WAC</span>
                    <span className="qc-kpi-value">
                      {stratMeta?.seasoned_wac != null
                        ? `${(Number(stratMeta.seasoned_wac) * 100).toFixed(2)}%`
                        : "—"}
                    </span>
                  </div>
                </div>
                <div
                  className="cf-grid-toolbar-actions strat-toolbar"
                  role="toolbar"
                  aria-label="Stratification Actions"
                >
                  <label className="field-inline strat-cohort-filter">
                    <span>Cohort</span>
                    <select
                      className="select"
                      value={stratCohort}
                      onChange={(e) => setStratCohort(e.target.value)}
                      aria-label="Cohort Filter"
                    >
                      <option value="all">All</option>
                      {(cohortStats || []).map((c) => (
                        <option key={c.cohort} value={c.cohort}>
                          {c.cohort}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className={`linkish${stratMetric === "upb" ? " is-active" : ""}`}
                    onClick={() => setStratMetric("upb")}
                  >
                    UPB
                  </button>
                  <button
                    type="button"
                    className={`linkish${stratMetric === "loans" ? " is-active" : ""}`}
                    onClick={() => setStratMetric("loans")}
                  >
                    Loans
                  </button>
                  <button
                    type="button"
                    className="cf-grid-icon-btn"
                    onClick={exportStratCsv}
                    title="Export CSV"
                    aria-label="Export CSV"
                    disabled={!stratRows.length}
                  >
                    <IconExportCsvMini />
                  </button>
                  <button
                    type="button"
                    className="cf-grid-icon-btn"
                    onClick={copyStratRows}
                    title="Copy"
                    aria-label="Copy Rows To Clipboard"
                    disabled={!stratRows.length}
                  >
                    <IconCopyMini />
                  </button>
                </div>
              </div>
              {stratLoading ? (
                <p className="muted">Loading Stratification…</p>
              ) : stratError ? (
                <StatusBanner tone="error">Stratification: {stratError}</StatusBanner>
              ) : (
                <>
                  <div className="strat-charts">
                    {stratDims.map((dim) => {
                      const wide =
                        dim.chart === "map" ||
                        dim.chart === "zip" ||
                        dim.chart === "line";
                      return (
                        <div
                          key={dim.id}
                          className={`strat-chart-panel${
                            wide ? " strat-chart-panel-wide" : ""
                          }`}
                        >
                          <div className="strat-chart-head">
                            <h3 className="strat-chart-title">{dim.label}</h3>
                          </div>
                          <StratDimChart
                            dim={dim}
                            rows={stratByDim[dim.id] || []}
                            metric={stratMetric}
                            selectedBucket={
                              stratDrill?.dimension === dim.id
                                ? stratDrill.bucket
                                : null
                            }
                            onBucketClick={(bucket) =>
                              onStratBucketClick(dim.id, bucket)
                            }
                          />
                        </div>
                      );
                    })}
                  </div>
                  {stratDrill && (
                    <div className="strat-drill qc-drill">
                      {stratDrillLoading ? (
                        <p className="muted">Loading Loans…</p>
                      ) : stratDrillError ? (
                        <StatusBanner tone="error">
                          Stratification Drill: {stratDrillError}
                        </StatusBanner>
                      ) : (
                        <DataGrid
                          rowData={stratDrillLoans}
                          columnDefs={qcDrillColumnDefs}
                          getRowId={(p) => String(p.data.loan_id)}
                          onRowDrill={drillLoan}
                          onRowStats={onStratDrillRowStats}
                          toolbarStart={stratDrillToolbarStart}
                          heightClass="grid-wrap-qc-drill"
                        />
                      )}
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {pane === "cohort" && (
            <>
              <section className="section section-cohort-chart">
                <div className="section-head section-head-stack">
                  <h2 className="section-title section-title-chart">
                    K-Prototypes (k=3, 4 Features): Original CLTV vs Refinance
                    Incentive
                  </h2>
                </div>
                <div className="chart-wrap chart-wrap-scatter">
                  {tapeLoading ? (
                    <p className="muted">Loading Tape…</p>
                  ) : tapeError ? (
                    <StatusBanner tone="error">Tape: {tapeError}</StatusBanner>
                  ) : (
                    <>
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          margin={{ top: 12, right: 16, left: 8, bottom: 28 }}
                        >
                          <CartesianGrid
                            stroke="#D0D7E2"
                            strokeDasharray="2 4"
                            strokeOpacity={0.9}
                          />
                          <XAxis
                            type="number"
                            dataKey="cltv"
                            name="Original CLTV"
                            tick={axisTick}
                            ticks={X_TICKS}
                            axisLine={{ stroke: "#8A9BB0" }}
                            tickLine={{ stroke: "#8A9BB0" }}
                            tickFormatter={(v) => Number(v).toFixed(1)}
                            domain={X_DOMAIN}
                            allowDataOverflow
                            label={{
                              value: "Original CLTV",
                              position: "insideBottom",
                              offset: -14,
                              fill: "#001A41",
                              fontSize: 11,
                              fontFamily: FONT,
                              fontWeight: 600,
                            }}
                          />
                          <YAxis
                            type="number"
                            dataKey="incentive"
                            name="Refinance Incentive"
                            tick={axisTick}
                            ticks={Y_TICKS}
                            axisLine={{ stroke: "#8A9BB0" }}
                            tickLine={{ stroke: "#8A9BB0" }}
                            domain={Y_DOMAIN}
                            allowDataOverflow
                            width={44}
                            label={{
                              value: "Refinance Incentive",
                              angle: -90,
                              position: "insideLeft",
                              offset: 8,
                              fill: "#001A41",
                              fontSize: 11,
                              fontFamily: FONT,
                              fontWeight: 600,
                            }}
                          />
                          <ZAxis range={[POINT_SIZE, POINT_SIZE]} />
                          <Tooltip
                            cursor={{
                              strokeDasharray: "3 3",
                              stroke: "#8A9BB0",
                            }}
                            contentStyle={{
                              background: "#FFFFFF",
                              border: "1px solid #D0D7E2",
                              borderRadius: 0,
                              fontSize: 11,
                              color: "#001A41",
                              fontFamily: FONT,
                            }}
                            labelStyle={{ color: "#4A5F7A" }}
                          />
                          <Legend
                            verticalAlign="top"
                            align="left"
                            wrapperStyle={{
                              position: "absolute",
                              top: 8,
                              left: 56,
                              width: "auto",
                              zIndex: 2,
                            }}
                            content={(props) => (
                              <CustomLegend
                                {...props}
                                activeCluster={clusterFilter}
                                onSelect={selectCluster}
                                counts={counts}
                              />
                            )}
                          />
                          <HullFills
                            hullSeries={hullSeries}
                            activeCluster={clusterFilter}
                          />
                          {CLUSTER_ORDER.map((code) => (
                            <Scatter
                              key={code}
                              name={code}
                              data={scatterByCluster[code]}
                              fill={CLUSTER_COLORS[code]}
                              fillOpacity={
                                clusterFilter === "all" ||
                                clusterFilter === code
                                  ? 0.75
                                  : 0.15
                              }
                              shape="circle"
                              onClick={() => selectCluster(code)}
                              cursor="pointer"
                              isAnimationActive={false}
                              legendType="circle"
                            />
                          ))}
                        </ComposedChart>
                      </ResponsiveContainer>
                      <aside
                        className="scatter-offaxis-note"
                        aria-label="Off-axis clustering features"
                      >
                        <span
                          className="scatter-offaxis-mark"
                          aria-hidden="true"
                        >
                          ★
                        </span>
                        <ul>
                          {OFF_AXIS_FEATURES.map((f) => (
                            <li key={f}>• {f}</li>
                          ))}
                        </ul>
                      </aside>
                    </>
                  )}
                </div>
              </section>

              <section className="section section-cohort-stats">
                <div className="section-head">
                  <h2 className="section-title">Cohort Statistics</h2>
                </div>
                {cohortStatsError ? (
                  <StatusBanner tone="muted">
                    Cohort stats: {cohortStatsError}
                  </StatusBanner>
                ) : (
                  <DataGrid
                    rowData={cohortStats}
                    columnDefs={cohortStatsColumnDefs}
                    getRowId={(p) => String(p.data.cohort)}
                    heightClass="grid-wrap-cohort-stats"
                    exportName="cohort-stats"
                  />
                )}
              </section>

              <section className="section section-fill">
                <div className="section-head">
                  <h2 className="section-title">Loans</h2>
                  <div className="section-actions">
                    <p className="section-meta">
                      Filter: {filterLabel}
                      {clusterFilter !== "all" && (
                        <>
                          {" · "}
                          <button
                            type="button"
                            className="linkish"
                            onClick={() => selectCluster("all")}
                          >
                            Clear
                          </button>
                        </>
                      )}
                      {" · "}
                      Ran Scenarios: {ranScenarioIds.length}/27
                    </p>
                  </div>
                </div>
                <DrillTrail crumbs={drillCrumbs} onJump={onDrillJump} />
                <DataGrid
                  rowData={filteredLoans}
                  columnDefs={loanColumnDefs}
                  getRowId={(p) => String(p.data.loanId)}
                  onRowDrill={drillLoan}
                  onGridReady={onGridReady}
                  scheduleSave={scheduleSave}
                  persistLayout
                  heightClass="grid-wrap-fill"
                  exportName="loans"
                />
              </section>
            </>
          )}

          {pane === "scenarios" && (
            <section className="section section-fill">
              <div className="section-head">
                <p className="section-meta">
                  {selectedCohort ? selectedCohort : "27 Cells"}
                </p>
                <div className="section-actions">
                  {(selectedCohort || selectedLoanId) && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={clearDrill}
                    >
                      Clear Drill
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn"
                    onClick={handleRunMonth1}
                    disabled={running}
                  >
                    {running ? "Running…" : "Run Month 1"}
                  </button>
                </div>
              </div>
              <DrillTrail crumbs={drillCrumbs} onJump={onDrillJump} />
              {runError && (
                <StatusBanner tone="error">Run: {runError}</StatusBanner>
              )}
              {neonNote && (
                <StatusBanner tone="muted">{neonNote}</StatusBanner>
              )}
              {runMeta && (
                <p className="section-meta">
                  Last {runMeta.executor || "run"} · wall{" "}
                  {Number(runMeta.wall_ms || 0).toFixed(0)} ms · ok=
                  {runMeta.ok}/{runMeta.n_tasks} · loan rows=
                  {runMeta.n_loan_rows ?? "—"}
                </p>
              )}
              <DataGrid
                rowData={filteredScenarios}
                columnDefs={scenarioColumnDefs}
                getRowId={(p) => String(p.data.scenario_id)}
                onRowDrill={drillScenario}
                heightClass="grid-wrap-fill"
                exportName="scenarios"
                gridProps={{ suppressRowTransform: true }}
              />
            </section>
          )}

          {pane === "cashflow" && (
            <section className="section section-fill">
              <div className="section-head">
                <p className="section-meta">
                  {cfView === "loanMonth"
                    ? "Multi-Month Loan Path"
                    : cfView === "month1"
                      ? "All Loans · Month 1"
                      : "Scenario Aggregates"}
                </p>
                <div className="section-actions">
                  <label className="field-inline">
                    <span>Scenario</span>
                    <select
                      className="select"
                      value={selectedScenarioId || ""}
                      onChange={(e) => {
                        setSelectedScenarioId(e.target.value);
                        setSelectedLoanId(null);
                        if (cfView === "agg") setCfView("month1");
                      }}
                    >
                      {scenarioOptions.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className={`linkish${cfView === "agg" ? " is-active" : ""}`}
                    onClick={() => {
                      setCfView("agg");
                      setSelectedLoanId(null);
                    }}
                  >
                    Aggregates
                  </button>
                  <button
                    type="button"
                    className={`linkish${cfView === "month1" ? " is-active" : ""}`}
                    onClick={() => {
                      setCfView("month1");
                      setSelectedLoanId(null);
                    }}
                  >
                    All Loans
                  </button>
                  {cfView === "loanMonth" && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => setCfView("month1")}
                    >
                      Back To Loans
                    </button>
                  )}
                  {(selectedLoanId || selectedCohort) && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={clearDrill}
                    >
                      Clear Drill
                    </button>
                  )}
                </div>
              </div>
              <DrillTrail crumbs={drillCrumbs} onJump={onDrillJump} />
              {cfView === "loanMonth" ? (
                loanMonthLoading ? (
                  <p className="muted">Loading multi-month CF…</p>
                ) : !loanMonthRows.length ? (
                  <p className="muted">
                    No multi-month rows for {selectedLoanId} /{" "}
                    {selectedScenarioId}. Run{" "}
                    <code>scripts/run_one_loan_cohort_axis.py</code> for this
                    loan×cohort axis.
                  </p>
                ) : (
                  <DataGrid
                    rowData={loanMonthRows}
                    columnDefs={loanMonthColumnDefs}
                    getRowId={(p) =>
                      `${p.data.scenario_id}|${p.data.loan_id}|${p.data.month}`
                    }
                    heightClass="grid-wrap-fill"
                    exportName="cf-loan-months"
                  />
                )
              ) : cfView === "month1" ? (
                neonCfLoading ? (
                  <p className="muted">Loading all-loan month-1 CF…</p>
                ) : !neonMonth1Rows.length ? (
                  <StatusBanner tone="muted">
                    No Neon month-1 rows for {selectedScenarioId}
                    {selectedLoanId ? ` / ${selectedLoanId}` : ""}. Open
                    Scenarios and Run month 1 (persists loan-level to Neon).
                  </StatusBanner>
                ) : (
                  <DataGrid
                    rowData={neonMonth1Rows}
                    columnDefs={cfMonth1ColumnDefs}
                    getRowId={(p) =>
                      `${p.data.scenario_id}|${p.data.loan_id}|${p.data.month}`
                    }
                    onRowDrill={drillMonth1Loan}
                    heightClass="grid-wrap-fill"
                    exportName="cf-month1-loans"
                  />
                )
              ) : !aggregates.length ? (
                <StatusBanner tone="muted">
                  No scenario aggregates yet. Open Scenarios and Run month 1.
                </StatusBanner>
              ) : (
                <DataGrid
                  rowData={aggregates}
                  columnDefs={aggColumnDefs}
                  getRowId={(p) => String(p.data.scenario_id)}
                  onRowDrill={drillAggScenario}
                  heightClass="grid-wrap-fill"
                  exportName="cf-aggregates"
                />
              )}
            </section>
          )}

          {pane === "assumptions" && (
            <section className="section section-fill">
              <div className="section-head">
                <p className="section-meta">
                  {assumptionMeta?.source || "data/assumptions.csv"}
                  {assumptionMeta?.n != null ? ` · ${assumptionMeta.n} rows` : ""}
                  {assumptionMeta?.bootstrap?.has_mi_all != null
                    ? ` · has_mi_all=${assumptionMeta.bootstrap.has_mi_all}`
                    : ""}
                  {" · CSV not DB"}
                </p>
              </div>
              {assumptionLoading ? (
                <p className="muted">Loading Assumptions…</p>
              ) : assumptionError ? (
                <StatusBanner tone="error">
                  Assumptions: {assumptionError}
                </StatusBanner>
              ) : !assumptionRows.length ? (
                <p className="muted">No assumptions loaded.</p>
              ) : (
                <DataGrid
                  rowData={assumptionRows}
                  columnDefs={assumptionColumnDefs}
                  getRowId={(p) => String(p.data.assumption_id)}
                  heightClass="grid-wrap-fill"
                  exportName="assumptions"
                />
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
