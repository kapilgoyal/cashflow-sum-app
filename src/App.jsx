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

/** Match matplotlib CLUSTER_META order (0→1→2). */
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

/** Domains/ticks aligned to labeled PNG. */
const X_DOMAIN = [0.28, 0.92];
const Y_DOMAIN = [-2.4, 3.2];
const X_TICKS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
const Y_TICKS = [-2, -1, 0, 1, 2, 3];

/** Matplotlib scatter s=28 → Recharts Z size (area). */
const POINT_SIZE = 28;

const OFF_AXIS_FEATURES = ["Documentation", "Remaining Term"];

const LS_CLUSTER_KEY = "cashflow.clusterFilter";
const LS_GRID_KEY = "cashflow.agGridState";

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
      <div className="scatter-legend-title">Cluster</div>
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

/** Filled convex hulls (matplotlib Polygon alpha=0.12, lw=1.2). */
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
  const [a, setA] = useState("2");
  const [b, setB] = useState("3");
  const [sum, setSum] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [loans, setLoans] = useState([]);
  const [hulls, setHulls] = useState({});
  const [counts, setCounts] = useState(CLUSTER_FALLBACK_COUNTS);
  const [tapeError, setTapeError] = useState(null);
  const [tapeLoading, setTapeLoading] = useState(true);
  const [clusterFilter, setClusterFilter] = useState(readClusterFilter);

  const gridApiRef = useRef(null);
  const restoringRef = useRef(false);
  const saveTimerRef = useRef(null);

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

  useEffect(() => {
    try {
      localStorage.setItem(LS_CLUSTER_KEY, clusterFilter);
    } catch {
      /* ignore */
    }
  }, [clusterFilter]);

  const columnDefs = useMemo(
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
        headerName: "Cluster",
        width: 100,
        filter: true,
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
      // Close ring for filled polygon
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

  async function handleSum() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/sum", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ a: Number(a), b: Number(b) }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setSum(data.sum);
    } catch (err) {
      setSum(null);
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  const axisTick = {
    fill: "#808080",
    fontSize: 10,
    fontFamily: FONT,
  };

  const filterLabel =
    clusterFilter === "all" ? "All clusters" : clusterFilter;

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
        <span className="topbar-version">v0.1.0</span>
      </header>

      <main className="main">
        <section className="section">
          <h2 className="section-title">Sum demo</h2>
          <div className="sum-row">
            <div className="field">
              <label htmlFor="input-a">A</label>
              <input
                id="input-a"
                type="number"
                value={a}
                onChange={(e) => setA(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="input-b">B</label>
              <input
                id="input-b"
                type="number"
                value={b}
                onChange={(e) => setB(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn"
              onClick={handleSum}
              disabled={loading}
            >
              {loading ? "Adding…" : "Add"}
            </button>
            {sum !== null && (
              <p className="result">
                Sum: <strong>{sum}</strong>
              </p>
            )}
            {error && <p className="error">Error: {error}</p>}
          </div>
        </section>

        <section className="section">
          <div className="section-head section-head-stack">
            <h2 className="section-title section-title-chart">
              K-Prototypes (k=3, 4 Features): Original CLTV vs Refinance
              Incentive
            </h2>
            <p className="scatter-subtitle">
              Original CLTV, Documentation, Remaining Term, Refinance Incentive
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
                      cursor={{ strokeDasharray: "3 3", stroke: "#464646" }}
                      contentStyle={{
                        background: "#212026",
                        border: "1px solid #323232",
                        borderRadius: 0,
                        fontSize: 11,
                        color: "#FCFCFC",
                        fontFamily: FONT,
                      }}
                      labelStyle={{ color: "#808080" }}
                      formatter={(value, name) => {
                        if (name === "cltv" || name === "Original CLTV") {
                          return [Number(value).toFixed(3), "Original CLTV"];
                        }
                        if (
                          name === "incentive" ||
                          name === "Refinance Incentive"
                        ) {
                          return [
                            Number(value).toFixed(3),
                            "Refinance Incentive",
                          ];
                        }
                        return [value, name];
                      }}
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
                          clusterFilter === "all" || clusterFilter === code
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
                  <span className="scatter-offaxis-mark" aria-hidden="true">
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
            <h2 className="section-title">Loan tape</h2>
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
            </p>
          </div>
          <div className="grid-wrap grid-wrap-tall ag-theme-cashflow">
            <AgGridReact
              theme={gridTheme}
              rowData={filteredLoans}
              columnDefs={columnDefs}
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
      </main>
    </div>
  );
}
