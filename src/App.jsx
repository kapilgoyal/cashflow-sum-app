import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
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
import {
  DataGrid,
  DrillTrail,
  FONT,
  StatusBanner,
  fmtInt,
  fmtNum,
  fmtPct,
  fmtUpbShort,
  fmtWac,
  intCol,
  moneyCol,
  pcaLabel,
  staLabel,
  withCohortPsaRowSpans,
} from "./cashflowGrid";
import { apiUrl } from "./apiBase";
import {
  CLUSTER_COLORS,
  CLUSTER_FALLBACK_COUNTS,
  CLUSTER_ORDER,
  cohortLabel,
  relabelCohortFields,
  remappedKeyedObject,
} from "./cohortLabels";
import LoanLevelCollateral from "./LoanLevelCollateral";
import LoanQc from "./LoanQc";
import InvestorAnalysis from "./InvestorAnalysis";
import ScenarioSpeedCharts from "./ScenarioSpeedCharts";
import "./App.css";


ModuleRegistry.registerModules([AllCommunityModule]);

const NAV = [
  { id: "asf", label: "Investor Tape" },
  { id: "qc", label: "Loan QC" },
  { id: "collateral", label: "Collateral" },
  { id: "investor", label: "Investor Analysis" },
  { id: "cohort", label: "Cohort" },
  { id: "scenarios", label: "Scenarios" },
  { id: "cashflow", label: "Cash Flow" },
  { id: "assumptions", label: "Assumptions" },
];

const X_DOMAIN = [0.28, 0.92];
const Y_DOMAIN = [-2.4, 3.2];
const X_TICKS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
const Y_TICKS = [-2, -1, 0, 1, 2, 3];
const POINT_SIZE = 28;
const LS_CLUSTER_KEY = "cashflow.clusterFilter";
const LS_GRID_KEY = "cashflow.agGridState";
const LS_NAV_KEY = "cashflow.navPane";
const LS_NAV_COLLAPSE_KEY = "cashflow.navCollapsed";

/** Compact stroke icons for sidenav (collapsed = icon only). */
function NavIcon({ id }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 16 16",
    fill: "none",
    "aria-hidden": "true",
    focusable: "false",
  };
  const stroke = {
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "square",
    strokeLinejoin: "miter",
  };
  switch (id) {
    case "asf":
      return (
        <svg {...common}>
          <path d="M2.5 3.5h11v9h-11z" {...stroke} />
          <path d="M2.5 6.5h11M5.5 3.5v9M8.5 6.5v6" {...stroke} />
        </svg>
      );
    case "qc":
      return (
        <svg {...common}>
          <path d="M3 8.2 6.2 11.5 13 4.5" {...stroke} />
        </svg>
      );
    case "strat":
      return (
        <svg {...common}>
          <path d="M3 12.5V7.5M7 12.5V3.5M11 12.5V5.5" {...stroke} />
          <path d="M2 12.5h12" {...stroke} />
        </svg>
      );
    case "collateral":
      return (
        <svg {...common}>
          <path d="M2.5 11.5 8 3.5l5.5 8H2.5z" {...stroke} />
          <path d="M5 11.5h6" {...stroke} />
        </svg>
      );
    case "investor":
      return (
        <svg {...common}>
          <path d="M3 12.5V5.5l5-3 5 3v7" {...stroke} />
          <path d="M6.5 12.5V8.5h3v4" {...stroke} />
        </svg>
      );
    case "cohort":
      return (
        <svg {...common}>
          <circle cx="5" cy="6" r="1.4" stroke="currentColor" strokeWidth="1.4" />
          <circle cx="11" cy="5" r="1.4" stroke="currentColor" strokeWidth="1.4" />
          <circle cx="8" cy="11" r="1.4" stroke="currentColor" strokeWidth="1.4" />
          <path d="M6.2 6.8 7.2 9.6M9.8 6.2 8.8 9.5" {...stroke} />
        </svg>
      );
    case "scenarios":
      return (
        <svg {...common}>
          <path d="M3 3.5h3.5V7H3zM9.5 3.5H13V7H9.5zM3 9h3.5v3.5H3zM9.5 9H13v3.5H9.5z" {...stroke} />
        </svg>
      );
    case "cashflow":
      return (
        <svg {...common}>
          <path d="M2.5 11.5 6 6.5l2.5 3 4.5-6" {...stroke} />
          <path d="M11 3.5h2.5V6" {...stroke} />
        </svg>
      );
    case "assumptions":
      return (
        <svg {...common}>
          <path d="M3.5 2.5h9v11h-9z" {...stroke} />
          <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" {...stroke} />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d="M3 8h10" {...stroke} />
        </svg>
      );
  }
}


function readClusterFilter() {
  // Always start with every cohort selected (not a single restored filter).
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
    if (v === "strat") return "collateral";
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
          const selected =
            activeCluster === "all" || activeCluster === code;
          const n = counts?.[code] ?? CLUSTER_FALLBACK_COUNTS[code] ?? "?";
          return (
            <li key={code}>
              <button
                type="button"
                className={`scatter-legend-btn${selected ? " is-active" : ""}`}
                style={{ "--cluster-color": entry.color }}
                onClick={() => onSelect(code)}
                title={`Filter to ${code}`}
                aria-pressed={selected}
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
            aria-pressed={activeCluster === "all"}
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


  const [cohortStats, setCohortStats] = useState([]);
  const [cohortStatsError, setCohortStatsError] = useState(null);

  const [scenarios, setScenarios] = useState([]);
  const [aggregates, setAggregates] = useState([]);
  const [ranScenarioIds, setRanScenarioIds] = useState([]);
  const [runMeta, setRunMeta] = useState(null);
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
        setLoans(
          (Array.isArray(data.loans) ? data.loans : []).map(relabelCohortFields)
        );
        setHulls(remappedKeyedObject(data.hulls || {}));
        if (data.meta?.counts) setCounts(remappedKeyedObject(data.meta.counts));
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
        setAsfLoans((data.loans || []).map(relabelCohortFields));
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

  // Cohort pool stats from Neon asf_tape.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/asf/cohort-stats"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setCohortStats((data.rows || []).map(relabelCohortFields));
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
          loadedFromNeon = true;
        } else if (neonStatusRes && !neonStatusRes.ok) {
        }

        if (neonScenRes?.ok) {
          const g = await neonScenRes.json();
          setScenarios((g.scenarios || []).map(relabelCohortFields));
          loadedFromNeon = true;
        } else {
          const gridRes = await fetch(apiUrl("/api/scenarios/grid")).catch(() => null);
          if (gridRes?.ok) {
            const g = await gridRes.json();
            setScenarios((g.scenarios || []).map(relabelCohortFields));
          }
        }
      } catch {
        /* offline — panes still usable */
      }

      try {
        const monthRes = await fetch(apiUrl("/api/cashflows/month1")).catch(() => null);
        if (!cancelled && monthRes?.ok) {
          const m = await monthRes.json();
          setAggregates((m.aggregates || []).map(relabelCohortFields));
          if (m.ran_scenario_ids?.length) {
            setRanScenarioIds(m.ran_scenario_ids);
          }
        } else {
          const staticRes = await fetch("/cohort-month1.json");
          if (!cancelled && staticRes.ok) {
            const m = await staticRes.json();
            setAggregates((m.aggregates || []).map(relabelCohortFields));
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
                    cohort: cohortLabel(a.cohort),
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
        setNeonMonth1Rows(rows.map(relabelCohortFields));
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
        if (!cancelled) setLoanMonthRows((data.rows || []).map(relabelCohortFields));
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


  const asfColumnDefs = useMemo(
    () => [
      {
        field: "loan_id",
        headerName: "Loan ID",
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
        valueFormatter: (p) => fmtWac(p.value),
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
        valueFormatter: (p) => fmtNum(p.value, 2),
        cellClass: "cf-num",
      },
      {
        field: "cohort",
        headerName: "Cohort",
        flex: 1.4,
        minWidth: 160,
        valueFormatter: (p) => cohortLabel(p.value),
      },
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
          {fmtInt(total)} {total === 1 ? "Loan" : "Loans"}
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
            {fmtInt(shown)} Shown
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


  const cohortStatsColumnDefs = useMemo(
    () => [
      {
        field: "cohort",
        headerName: "Cohort",
        flex: 1.8,
        minWidth: 160,
        valueFormatter: (p) => cohortLabel(p.value),
      },
      intCol("loan_count", "Loans", 80),
      moneyCol("upb", "UPB", 120),
      {
        field: "wac",
        headerName: "WAC",
        width: 88,
        valueGetter: (p) => p.data?.wac ?? p.data?.avg_rate,
        valueFormatter: (p) => fmtWac(p.value),
        cellClass: "cf-num",
      },
      {
        field: "wam",
        headerName: "WAM",
        width: 88,
        valueGetter: (p) => p.data?.wam ?? p.data?.avg_remaining_term,
        valueFormatter: (p) => fmtInt(p.value),
        cellClass: "cf-num",
      },
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
      intCol("avg_fico", "Avg FICO", 88),
      {
        field: "avg_refi_incentive",
        headerName: "Avg Refi",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "avg_remaining_term",
        headerName: "Avg Rem",
        width: 88,
        valueFormatter: (p) => fmtInt(p.value),
        cellClass: "cf-num",
      },
    ],
    []
  );

  const cohortKpis = useMemo(() => {
    const rows = (cohortStats || []).filter(
      (r) =>
        clusterFilter === "all" || cohortLabel(r.cohort) === clusterFilter
    );
    const loanCount = rows.reduce((s, r) => s + (Number(r.loan_count) || 0), 0);
    const upb = rows.reduce((s, r) => s + (Number(r.upb) || 0), 0);
    const upbWeighted = (getter) => {
      if (upb <= 0) return null;
      let num = 0;
      let den = 0;
      for (const r of rows) {
        const w = Number(r.upb) || 0;
        const v = getter(r);
        if (!(w > 0) || v == null || Number.isNaN(Number(v))) continue;
        num += Number(v) * w;
        den += w;
      }
      return den > 0 ? num / den : null;
    };
    return {
      loanCount,
      upb,
      wac: upbWeighted((r) => r.wac ?? r.avg_rate),
      wam: upbWeighted((r) => r.wam ?? r.avg_remaining_term),
      avgLtv: upbWeighted((r) => r.avg_ltv),
      avgFico: upbWeighted((r) => r.avg_fico),
      avgRi: upbWeighted((r) => r.avg_refi_incentive),
    };
  }, [cohortStats, clusterFilter]);

  const scenarioColumnDefs = useMemo(
    () => [
      {
        field: "cohort",
        headerName: "Cohort Name",
        flex: 1.6,
        minWidth: 132,
        sortable: false,
        filter: false,
        rowSpan: (p) => Math.max(1, p.data?._cohortSpan || 1),
        cellClassRules: {
          "cf-row-span": (p) => (p.data?._cohortSpan || 0) > 1,
        },
        valueGetter: (p) =>
          p.data?._cohortSpan === 0
            ? ""
            : cohortLabel(p.data?.cohort) || "",
      },
      {
        field: "psa_multiple",
        headerName: "PSA",
        width: 64,
        sortable: false,
        filter: false,
        type: "numericColumn",
        cellClass: "cf-num",
        rowSpan: (p) => Math.max(1, p.data?._psaSpan || 1),
        cellClassRules: {
          "cf-row-span": (p) => (p.data?._psaSpan || 0) > 1,
          "cf-num": () => true,
        },
        valueGetter: (p) =>
          p.data?._psaSpan === 0 ? "" : p.data?.psa_multiple,
        valueFormatter: (p) =>
          p.value === "" || p.value == null ? "" : fmtInt(p.value),
      },
      intCol("sda_multiple", "SDA", 64),
      {
        field: "recovery",
        headerName: "Recovery Rate",
        width: 104,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "lag",
        headerName: "Fnma Lag",
        width: 84,
        valueFormatter: (p) =>
          p.value == null || Number.isNaN(Number(p.value))
            ? ""
            : `${Number(p.value).toFixed(0)} Mo`,
        cellClass: "cf-num",
      },
      { field: "scenario_id", headerName: "ID", hide: true },
    ],
    []
  );

  const aggColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", hide: true },
      {
        field: "cohort",
        headerName: "Cohort",
        flex: 1.6,
        minWidth: 180,
        valueFormatter: (p) => cohortLabel(p.value),
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
      {
        field: "cohort",
        headerName: "Cohort",
        flex: 1.4,
        minWidth: 160,
        valueFormatter: (p) => cohortLabel(p.value),
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
            valueFormatter: (p) => fmtPct(p.value, 1),
            cellClass: "cf-num",
          },
          {
            field: "cdr",
            headerName: "CDR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 2),
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
        valueFormatter: (p) => fmtPct(p.value, 1),
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
            valueFormatter: (p) => fmtPct(p.value, 1),
            cellClass: "cf-num",
          },
          {
            field: "cdr",
            headerName: "CDR",
            width: 72,
            valueFormatter: (p) => fmtPct(p.value, 2),
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

  /** Full 27-cell grid — never cohort-filtered; Scenarios is a standalone view. */
  const scenarioRows = useMemo(() => {
    const byCohort = Object.fromEntries(
      (cohortStats || []).map((r) => [cohortLabel(r.cohort), r])
    );
    const base = (
      scenarios.length
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
            avg_used_recovery_lag_months: a.avg_used_recovery_lag_months,
          }))
    ).map((s) => {
      const stats = byCohort[cohortLabel(s.cohort)] || {};
      const recovery = stats.recovery ?? s.recovery_rate;
      const lag =
        stats.lag ??
        s.avg_used_recovery_lag_months ??
        s.recovery_lag_months ??
        null;
      return {
        ...s,
        cohort: cohortLabel(s.cohort),
        recovery,
        lag,
      };
    });
    return withCohortPsaRowSpans(base);
  }, [scenarios, aggregates, cohortStats]);

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
    const cohort = cohortLabel(row.cluster || row.cohort || "") || null;
    setSelectedLoanId(loanId || null);
    setSelectedCohort(cohort);
    if (cohort) setClusterFilter(cohort);
    setCfView("month1");
    setPane("cashflow");
  }, []);

  const drillAggScenario = useCallback((row) => {
    if (!row?.scenario_id) return;
    setSelectedScenarioId(row.scenario_id);
    if (row.cohort) setSelectedCohort(cohortLabel(row.cohort));
    setSelectedLoanId(null);
    setCfView("month1");
  }, []);

  const drillMonth1Loan = useCallback((row) => {
    if (!row?.loan_id || !row?.scenario_id) return;
    setSelectedLoanId(row.loan_id);
    setSelectedScenarioId(row.scenario_id);
    if (row.cohort) setSelectedCohort(cohortLabel(row.cohort));
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
        label: cohortLabel(selectedCohort),
        jumpable: false,
      });
    }
    crumbs.push({ id: "agg", label: "CF Aggregates", jumpable: cfView !== "agg" });
    if (selectedScenarioId && cfView !== "agg") {
      const row =
        (scenarios || []).find((s) => s.scenario_id === selectedScenarioId) ||
        (aggregates || []).find((s) => s.scenario_id === selectedScenarioId);
      const scenarioLabel = row
        ? `${cohortLabel(row.cohort)} PSA ${row.psa_multiple} / SDA ${row.sda_multiple}`
        : "";
      if (scenarioLabel) {
        crumbs.push({
          id: "scenario",
          label: scenarioLabel,
          jumpable: false,
        });
      }
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
  }, [
    selectedCohort,
    selectedScenarioId,
    selectedLoanId,
    cfView,
    scenarios,
    aggregates,
  ]);

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
      setAggregates((data.aggregates || []).map(relabelCohortFields));
      setRanScenarioIds(data.ran_scenario_ids || []);
      setRunMeta(data.parallelism || null);
      if (data.aggregates?.length && !scenarios.length) {
        setScenarios(
          data.aggregates.map((a) => ({
            scenario_id: a.scenario_id,
            cohort: cohortLabel(a.cohort),
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

  const scenarioDisplayName = useCallback(
    (id) => {
      const row =
        (scenarios || []).find((s) => s.scenario_id === id) ||
        (aggregates || []).find((s) => s.scenario_id === id);
      if (!row) return "";
      return `${cohortLabel(row.cohort)} PSA ${row.psa_multiple} / SDA ${row.sda_multiple}`;
    },
    [scenarios, aggregates]
  );

  const scenarioOptions = useMemo(() => {
    const ids = (
      scenarios.length
        ? scenarios
        : aggregates.map((a) => ({
            scenario_id: a.scenario_id,
            cohort: a.cohort,
            psa_multiple: a.psa_multiple,
            sda_multiple: a.sda_multiple,
          }))
    ).map((s) => ({
      id: s.scenario_id,
      label: `${cohortLabel(s.cohort)} PSA ${s.psa_multiple} / SDA ${s.sda_multiple}`,
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
                <NavIcon id={item.id} />
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

          {pane === "qc" && <LoanQc onDrillLoan={drillLoan} />}

          {pane === "collateral" && <LoanLevelCollateral />}

          {pane === "investor" && <InvestorAnalysis />}

          {pane === "cohort" && (
            <>
              <section className="section section-cohort-chart">
                <div className="section-head">
                  <h2 className="section-title section-title-chart">
                    Original CLTV vs Refinance Incentive
                  </h2>
                  {clusterFilter !== "all" && (
                    <div className="section-actions">
                      <button
                        type="button"
                        className="linkish"
                        onClick={() => selectCluster("all")}
                      >
                        Clear {clusterFilter}
                      </button>
                    </div>
                  )}
                </div>
                <div className="cohort-chart-row">
                  <div className="chart-wrap chart-wrap-scatter">
                    {tapeLoading ? (
                      <p className="muted">Loading Cohort Chart…</p>
                    ) : tapeError ? (
                      <StatusBanner tone="error">Tape: {tapeError}</StatusBanner>
                    ) : !loans.length ? (
                      <p className="muted">No Cohort Points Loaded.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          margin={{ top: 12, right: 16, left: 8, bottom: 28 }}
                        >
                          <CartesianGrid
                            stroke="#323232"
                            strokeDasharray="2 4"
                            strokeOpacity={0.9}
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
                              stroke: "#323232",
                            }}
                            contentStyle={{
                              background: "#0C0C0C",
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
                    )}
                  </div>
                  <aside
                    className="cohort-kpi-rail"
                    role="toolbar"
                    aria-label="Cohort KPIs"
                  >
                    <button
                      type="button"
                      className={`qc-kpi cohort-kpi${
                        clusterFilter === "all" ? " is-active" : ""
                      }`}
                      aria-label="Total Loans"
                      onClick={() => selectCluster("all")}
                    >
                      <span className="qc-kpi-label">Total Loans</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.loanCount
                          ? fmtInt(cohortKpis.loanCount)
                          : "—"}
                      </span>
                    </button>
                    <div className="qc-kpi cohort-kpi" aria-label="UPB">
                      <span className="qc-kpi-label">UPB</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.upb ? fmtUpbShort(cohortKpis.upb) : "—"}
                      </span>
                    </div>
                    <div className="qc-kpi cohort-kpi" aria-label="WAC">
                      <span className="qc-kpi-label">WAC</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.wac != null
                          ? fmtWac(cohortKpis.wac)
                          : "—"}
                      </span>
                    </div>
                    <div className="qc-kpi cohort-kpi" aria-label="WAM">
                      <span className="qc-kpi-label">WAM</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.wam != null
                          ? `${fmtInt(cohortKpis.wam)} Mo`
                          : "—"}
                      </span>
                    </div>
                    <div className="qc-kpi cohort-kpi" aria-label="Avg LTV">
                      <span className="qc-kpi-label">Avg LTV</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.avgLtv != null
                          ? fmtPct(cohortKpis.avgLtv, 1)
                          : "—"}
                      </span>
                    </div>
                    <div className="qc-kpi cohort-kpi" aria-label="Avg FICO">
                      <span className="qc-kpi-label">Avg FICO</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.avgFico != null
                          ? fmtInt(cohortKpis.avgFico)
                          : "—"}
                      </span>
                    </div>
                    <div className="qc-kpi cohort-kpi" aria-label="Avg RI">
                      <span className="qc-kpi-label">Avg RI</span>
                      <span className="qc-kpi-value">
                        {cohortKpis.avgRi != null
                          ? fmtNum(cohortKpis.avgRi, 1)
                          : "—"}
                      </span>
                    </div>
                  </aside>
                </div>
              </section>

              <section className="section section-cohort-stats section-fill">
                <div className="section-head">
                  <h2 className="section-title">Cohort Statistics</h2>
                </div>
                {cohortStatsError ? (
                  <StatusBanner tone="error">
                    Cohort Stats: {cohortStatsError}
                  </StatusBanner>
                ) : !cohortStats.length ? (
                  <p className="muted">No Cohort Statistics Loaded.</p>
                ) : (
                  <DataGrid
                    rowData={
                      clusterFilter === "all"
                        ? cohortStats
                        : cohortStats.filter(
                            (r) => cohortLabel(r.cohort) === clusterFilter
                          )
                    }
                    columnDefs={cohortStatsColumnDefs}
                    getRowId={(p) => String(p.data.cohort)}
                    onRowDrill={(row) =>
                      selectCluster(cohortLabel(row.cohort) || "all")
                    }
                    heightClass="grid-wrap-cohort-stats"
                    exportName="cohort-stats"
                  />
                )}
              </section>
            </>
          )}

          {pane === "scenarios" && (
            <section className="section section-fill">
              <div className="section-head">
                <p className="section-meta">27 Cells</p>
              </div>
              <div className="scenario-layout">
                <DataGrid
                  rowData={scenarioRows}
                  columnDefs={scenarioColumnDefs}
                  getRowId={(p) => String(p.data.scenario_id)}
                  heightClass="grid-wrap-fill scenario-grid"
                  exportName="scenarios"
                  showToolbar={false}
                  gridProps={{ suppressRowTransform: true }}
                />
                <ScenarioSpeedCharts />
              </div>
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
                  <p className="muted">Loading Multi-Month CF…</p>
                ) : !loanMonthRows.length ? (
                  <p className="muted">
                    No Multi-Month Rows For {selectedLoanId}
                    {selectedScenarioId
                      ? ` / ${scenarioDisplayName(selectedScenarioId)}`
                      : ""}
                    .
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
                  <p className="muted">Loading All-Loan Month 1 CF…</p>
                ) : !neonMonth1Rows.length ? (
                  <StatusBanner tone="muted">
                    No Month 1 Rows For {scenarioDisplayName(selectedScenarioId)}
                    {selectedLoanId ? ` / ${selectedLoanId}` : ""}. Open
                    Scenarios.
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
                  No Scenario Aggregates Yet. Open Scenarios.
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
                  Assumptions
                </p>
              </div>
              {assumptionLoading ? (
                <p className="muted">Loading Assumptions…</p>
              ) : assumptionError ? (
                <StatusBanner tone="error">
                  Assumptions: {assumptionError}
                </StatusBanner>
              ) : !assumptionRows.length ? (
                <p className="muted">No Assumptions Loaded.</p>
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
