import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
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
import "./App.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const FONT = '"Source Sans 3", "Segoe UI", system-ui, sans-serif';

const NAV = [
  { id: "loan", label: "Loan" },
  { id: "scenarios", label: "Cash Flow Scenarios" },
  { id: "cashflow", label: "Cash Flow" },
];

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

const gridTheme = themeQuartz.withParams({
  backgroundColor: "#212026",
  foregroundColor: "#FCFCFC",
  headerBackgroundColor: "#0C0C0C",
  headerTextColor: "#808080",
  oddRowBackgroundColor: "#121212",
  rowHoverColor: "#1A1A1A",
  selectedRowBackgroundColor: "#1E1E22",
  borderColor: "#323232",
  rowBorder: { style: "solid", width: 1, color: "#323232" },
  columnBorder: { style: "solid", width: 1, color: "#2A2A2A" },
  headerColumnBorder: false,
  fontFamily: FONT,
  fontSize: 11,
  headerFontSize: 10,
  headerFontWeight: 600,
  spacing: 2,
  headerHeight: 22,
  rowHeight: 22,
  borderRadius: 0,
  wrapperBorderRadius: 0,
});

function readClusterFilter() {
  try {
    const v = localStorage.getItem(LS_CLUSTER_KEY);
    if (v === "all" || CLUSTER_ORDER.includes(v)) return v;
  } catch {
    /* ignore */
  }
  return "all";
}

function readNav() {
  try {
    const v = localStorage.getItem(LS_NAV_KEY);
    if (NAV.some((n) => n.id === v)) return v;
  } catch {
    /* ignore */
  }
  return "loan";
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

function fmtMoney(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
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
  const [loans, setLoans] = useState([]);
  const [hulls, setHulls] = useState({});
  const [counts, setCounts] = useState(CLUSTER_FALLBACK_COUNTS);
  const [tapeError, setTapeError] = useState(null);
  const [tapeLoading, setTapeLoading] = useState(true);
  const [clusterFilter, setClusterFilter] = useState(readClusterFilter);

  const [scenarios, setScenarios] = useState([]);
  const [aggregates, setAggregates] = useState([]);
  const [ranScenarioIds, setRanScenarioIds] = useState([]);
  const [runMeta, setRunMeta] = useState(null);
  const [neonNote, setNeonNote] = useState(null);
  const [runError, setRunError] = useState(null);
  const [running, setRunning] = useState(false);

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

  // Load scenario grid + any precomputed month-1 aggregates into memory (no full reload).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [gridRes, monthRes] = await Promise.all([
          fetch("/api/scenarios/grid").catch(() => null),
          fetch("/cohort-month1.json").catch(() => null),
        ]);
        if (cancelled) return;
        if (gridRes?.ok) {
          const g = await gridRes.json();
          setScenarios(g.scenarios || []);
        } else {
          // Static fallback from public if API down
          const staticScenarios = await fetch("/cohort-month1.json")
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null);
          if (staticScenarios?.aggregates) {
            setScenarios(
              staticScenarios.aggregates.map((a) => ({
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
        if (monthRes?.ok) {
          const m = await monthRes.json();
          setAggregates(m.aggregates || []);
          setRanScenarioIds(
            (m.meta?.ran_scenario_ids || m.aggregates || [])
              .map((x) => (typeof x === "string" ? x : x.scenario_id))
              .filter(Boolean)
          );
          setRunMeta(m.meta?.parallelism || null);
          setNeonNote(m.neon_note || null);
        }
      } catch {
        /* offline — panes still usable */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LS_CLUSTER_KEY, clusterFilter);
    } catch {
      /* ignore */
    }
  }, [clusterFilter]);

  const loanColumnDefs = useMemo(
    () => [
      { field: "loanId", headerName: "Loan ID", flex: 1.1, minWidth: 100 },
      {
        field: "fico",
        headerName: "FICO",
        width: 72,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
      },
      {
        field: "cltv",
        headerName: "CLTV",
        width: 90,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) =>
          p.value == null ? "" : `${(Number(p.value) * 100).toFixed(1)}%`,
      },
      {
        field: "documentation",
        headerName: "Documentation",
        flex: 1.2,
        minWidth: 120,
        filter: true,
      },
      {
        field: "remainingTerm",
        headerName: "Remaining term",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
      },
      {
        field: "refinanceIncentive",
        headerName: "Refi incentive",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) =>
          p.value == null ? "" : Number(p.value).toFixed(3),
      },
      {
        field: "cluster",
        headerName: "Cohort",
        flex: 1.6,
        minWidth: 180,
        filter: true,
      },
    ],
    []
  );

  const scenarioColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", width: 64 },
      { field: "cohort", headerName: "Cohort", flex: 1.8, minWidth: 200 },
      {
        field: "pca_level",
        headerName: "PCA",
        width: 70,
        valueGetter: (p) =>
          p.data.pca_level ||
          ({ 75: "Down", 100: "Base", 125: "Up" }[p.data.psa_multiple] ??
            p.data.psa_multiple),
      },
      {
        field: "sta_level",
        headerName: "STA",
        width: 70,
        valueGetter: (p) =>
          p.data.sta_level ||
          ({ 50: "Down", 100: "Base", 200: "Up" }[p.data.sda_multiple] ??
            p.data.sda_multiple),
      },
      {
        field: "psa_multiple",
        headerName: "PSA",
        width: 64,
        type: "numericColumn",
      },
      {
        field: "sda_multiple",
        headerName: "SDA",
        width: 64,
        type: "numericColumn",
      },
      {
        field: "recovery_rate",
        headerName: "Rec %",
        width: 72,
        valueFormatter: (p) =>
          p.value == null ? "" : `${(Number(p.value) * 100).toFixed(0)}%`,
      },
      {
        field: "recovery_period_months",
        headerName: "Rec mos",
        width: 80,
        type: "numericColumn",
      },
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

  const cfColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", width: 64 },
      { field: "cohort", headerName: "Cohort", flex: 1.6, minWidth: 180 },
      { field: "pca_level", headerName: "PCA", width: 64 },
      { field: "sta_level", headerName: "STA", width: 64 },
      {
        field: "n_loans",
        headerName: "Loans",
        width: 70,
        type: "numericColumn",
      },
      {
        field: "beginning_balance",
        headerName: "Begin bal",
        width: 110,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "interest",
        headerName: "Interest",
        width: 100,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "scheduled_principal",
        headerName: "Sched prin",
        width: 100,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "default",
        headerName: "Default",
        width: 90,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "prepay",
        headerName: "Prepay",
        width: 90,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "recovery",
        headerName: "Recovery",
        width: 90,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
      {
        field: "ending_balance",
        headerName: "End bal",
        width: 110,
        type: "numericColumn",
        valueFormatter: (p) => fmtMoney(p.value),
      },
    ],
    []
  );

  const defaultColDef = useMemo(
    () => ({
      sortable: true,
      resizable: true,
      filter: true,
      suppressMovable: false,
    }),
    []
  );

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

  const scenarioRows = useMemo(() => {
    if (scenarios.length) return scenarios;
    return aggregates.map((a) => ({
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
  }, [scenarios, aggregates]);

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
  }, []);

  async function handleRunMonth1() {
    setRunning(true);
    setRunError(null);
    try {
      const res = await fetch("/api/cashflows/run-month1", { method: "POST" });
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
          ? "DATABASE_URL not set — loan-level CF in SQLite/JSON under data/"
          : data.storage?.neon || null
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
      setPane("cashflow");
    } catch (err) {
      setRunError(err.message || String(err));
    } finally {
      setRunning(false);
    }
  }

  const axisTick = {
    fill: "#808080",
    fontSize: 10,
    fontFamily: FONT,
  };

  const filterLabel =
    clusterFilter === "all" ? "All cohorts" : clusterFilter;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-brand">
          <img
            className="topbar-mark"
            src="/favicon.svg"
            alt=""
            width={16}
            height={16}
          />
          <span className="topbar-name">CashFlow</span>
        </div>
        <span className="topbar-version">v0.2.0</span>
      </header>

      <div className="shell">
        <nav className="sidenav" aria-label="Primary">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`sidenav-btn${pane === item.id ? " is-active" : ""}`}
              onClick={() => selectPane(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="main">
          {pane === "loan" && (
            <>
              <section className="section">
                <div className="section-head section-head-stack">
                  <h2 className="section-title section-title-chart">
                    K-Prototypes (k=3, 4 Features): Original CLTV vs Refinance
                    Incentive
                  </h2>
                  <p className="scatter-subtitle">
                    Cohorts: high LTV + strong / high LTV + weak / low LTV +
                    weak refinance incentive
                  </p>
                </div>
                <div className="chart-wrap chart-wrap-scatter">
                  {tapeLoading ? (
                    <p className="muted">Loading tape…</p>
                  ) : tapeError ? (
                    <p className="error">Tape: {tapeError}</p>
                  ) : (
                    <>
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          margin={{ top: 12, right: 16, left: 8, bottom: 28 }}
                        >
                          <CartesianGrid
                            stroke="#464646"
                            strokeDasharray="2 4"
                            strokeOpacity={0.45}
                          />
                          <XAxis
                            type="number"
                            dataKey="cltv"
                            name="Original CLTV"
                            tick={axisTick}
                            ticks={X_TICKS}
                            axisLine={{ stroke: "#323232" }}
                            tickLine={{ stroke: "#323232" }}
                            tickFormatter={(v) => Number(v).toFixed(1)}
                            domain={X_DOMAIN}
                            allowDataOverflow
                            label={{
                              value: "Original CLTV",
                              position: "insideBottom",
                              offset: -14,
                              fill: "#FCFCFC",
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
                            axisLine={{ stroke: "#323232" }}
                            tickLine={{ stroke: "#323232" }}
                            domain={Y_DOMAIN}
                            allowDataOverflow
                            width={44}
                            label={{
                              value: "Refinance Incentive",
                              angle: -90,
                              position: "insideLeft",
                              offset: 8,
                              fill: "#FCFCFC",
                              fontSize: 11,
                              fontFamily: FONT,
                              fontWeight: 600,
                            }}
                          />
                          <ZAxis range={[POINT_SIZE, POINT_SIZE]} />
                          <Tooltip
                            cursor={{
                              strokeDasharray: "3 3",
                              stroke: "#464646",
                            }}
                            contentStyle={{
                              background: "#212026",
                              border: "1px solid #323232",
                              borderRadius: 0,
                              fontSize: 11,
                              color: "#FCFCFC",
                              fontFamily: FONT,
                            }}
                            labelStyle={{ color: "#808080" }}
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

              <section className="section">
                <div className="section-head">
                  <h2 className="section-title">Loans</h2>
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
                    Ran scenarios: {ranScenarioIds.length}/27
                  </p>
                </div>
                <div className="grid-wrap grid-wrap-tall ag-theme-cashflow">
                  <AgGridReact
                    theme={gridTheme}
                    rowData={filteredLoans}
                    columnDefs={loanColumnDefs}
                    defaultColDef={defaultColDef}
                    suppressCellFocus
                    animateRows={false}
                    onGridReady={onGridReady}
                    onColumnMoved={scheduleSave}
                    onColumnVisible={scheduleSave}
                    onColumnPinned={scheduleSave}
                    onColumnResized={scheduleSave}
                    onSortChanged={scheduleSave}
                    onFilterChanged={scheduleSave}
                    getRowId={(p) => String(p.data.loanId)}
                  />
                </div>
              </section>
            </>
          )}

          {pane === "scenarios" && (
            <section className="section">
              <div className="section-head">
                <h2 className="section-title">Cash Flow Scenarios</h2>
                <div className="section-actions">
                  <p className="section-meta">
                    27 cells · cohort × PCA × STA · month 1 · 27 workers
                  </p>
                  <button
                    type="button"
                    className="btn"
                    onClick={handleRunMonth1}
                    disabled={running}
                  >
                    {running ? "Running…" : "Run month 1"}
                  </button>
                </div>
              </div>
              {runError && <p className="error">Run: {runError}</p>}
              {neonNote && <p className="muted">{neonNote}</p>}
              {runMeta && (
                <p className="section-meta">
                  Last wall {Number(runMeta.wall_ms).toFixed(0)} ms · ok=
                  {runMeta.ok}/{runMeta.n_tasks} · loan rows=
                  {runMeta.n_loan_rows ?? "—"}
                </p>
              )}
              <div className="grid-wrap grid-wrap-tall ag-theme-cashflow">
                <AgGridReact
                  theme={gridTheme}
                  rowData={scenarioRows}
                  columnDefs={scenarioColumnDefs}
                  defaultColDef={defaultColDef}
                  suppressCellFocus
                  animateRows={false}
                  getRowId={(p) => String(p.data.scenario_id)}
                />
              </div>
            </section>
          )}

          {pane === "cashflow" && (
            <section className="section">
              <div className="section-head">
                <h2 className="section-title">Cash Flow</h2>
                <p className="section-meta">
                  Cohort-level month-1 summaries
                  {aggregates.length
                    ? ` · ${aggregates.length} scenarios`
                    : " · not run yet"}
                </p>
              </div>
              {!aggregates.length ? (
                <p className="muted">
                  No month-1 results in memory. Open Cash Flow Scenarios and
                  click Run month 1.
                </p>
              ) : (
                <div className="grid-wrap grid-wrap-tall ag-theme-cashflow">
                  <AgGridReact
                    theme={gridTheme}
                    rowData={aggregates}
                    columnDefs={cfColumnDefs}
                    defaultColDef={defaultColDef}
                    suppressCellFocus
                    animateRows={false}
                    getRowId={(p) => String(p.data.scenario_id)}
                  />
                </div>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
