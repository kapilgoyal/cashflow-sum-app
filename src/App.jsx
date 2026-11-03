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
  fmtNum,
  fmtPct,
  intCol,
  moneyCol,
  pcaLabel,
  staLabel,
  withScenarioRowSpans,
} from "./cashflowGrid";
import "./App.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const NAV = [
  { id: "asf", label: "ASF Tape" },
  { id: "qc", label: "Loan QC" },
  { id: "strat", label: "Stratification" },
  { id: "cohort", label: "Cohort" },
  { id: "scenarios", label: "Scenarios" },
  { id: "cashflow", label: "Cash Flow" },
  { id: "assumptions", label: "Assumptions" },
];

const STRAT_DIMS = [
  { id: "documentation_type", label: "Documentation" },
  { id: "ltv_bucket", label: "LTV bucket" },
  { id: "cltv_bucket", label: "CLTV bucket" },
  { id: "fico_band", label: "FICO band" },
  { id: "state", label: "State" },
  { id: "property_type", label: "Property type" },
  { id: "occupancy", label: "Occupancy" },
  { id: "loan_purpose", label: "Loan purpose" },
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
  const [loans, setLoans] = useState([]);
  const [hulls, setHulls] = useState({});
  const [counts, setCounts] = useState(CLUSTER_FALLBACK_COUNTS);
  const [tapeError, setTapeError] = useState(null);
  const [tapeLoading, setTapeLoading] = useState(true);
  const [clusterFilter, setClusterFilter] = useState(readClusterFilter);

  const [asfLoans, setAsfLoans] = useState([]);
  const [asfTotal, setAsfTotal] = useState(0);
  const [asfSource, setAsfSource] = useState(null);
  const [asfLoading, setAsfLoading] = useState(false);
  const [asfError, setAsfError] = useState(null);

  const [stratRows, setStratRows] = useState([]);
  const [stratMeta, setStratMeta] = useState(null);
  const [stratLoading, setStratLoading] = useState(false);
  const [stratError, setStratError] = useState(null);

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
        const res = await fetch("/api/asf/tape?limit=2000");
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        if (cancelled) return;
        setAsfLoans(data.loans || []);
        setAsfTotal(data.total ?? (data.loans || []).length);
        setAsfSource(data.source || null);
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
      try {
        const results = await Promise.all(
          STRAT_DIMS.map(async (dim) => {
            const res = await fetch(
              `/api/asf/stratification?by=${encodeURIComponent(dim.id)}`
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
        const combined = [];
        let tape_row_count = null;
        let tape_upb = null;
        for (const { dim, data } of results) {
          if (tape_row_count == null && data.tape_row_count != null) {
            tape_row_count = data.tape_row_count;
          }
          if (tape_upb == null && data.tape_upb != null) {
            tape_upb = data.tape_upb;
          }
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
          n_dimensions: STRAT_DIMS.length,
          n_buckets: combined.length,
          tape_row_count,
          tape_upb,
        });
      } catch (err) {
        if (!cancelled) {
          setStratError(err.message || String(err));
          setStratRows([]);
          setStratMeta(null);
        }
      } finally {
        if (!cancelled) setStratLoading(false);
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
        const res = await fetch("/api/asf/cohort-stats");
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
          fetch("/api/neon/scenarios").catch(() => null),
          fetch("/api/neon/status").catch(() => null),
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
          const gridRes = await fetch("/api/scenarios/grid").catch(() => null);
          if (gridRes?.ok) {
            const g = await gridRes.json();
            setScenarios(g.scenarios || []);
          }
        }
      } catch {
        /* offline — panes still usable */
      }

      try {
        const monthRes = await fetch("/api/cashflows/month1").catch(() => null);
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
          `/api/neon/cashflows/month1?scenario_id=${encodeURIComponent(
            selectedScenarioId
          )}&limit=5000`
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
        const res = await fetch(`/api/neon/cashflows/loan-month?${qs}`);
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
        const res = await fetch("/api/qc/results");
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
        const res = await fetch("/api/assumptions");
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

  const qcSummary = useMemo(() => {
    const pass = qcRows.filter((r) => r.outcome === "pass").length;
    const fail = qcRows.filter((r) => r.outcome === "fail").length;
    const skipped = qcRows.filter((r) => r.outcome === "skipped").length;
    const scored = pass + fail;
    const pct = scored ? (100 * pass) / scored : null;
    return { pass, fail, skipped, scored, pct };
  }, [qcRows]);

  const asfColumnDefs = useMemo(
    () => [
      { field: "loan_id", headerName: "Loan", width: 100, cellClass: "cf-id" },
      moneyCol("current_loan_amount", "UPB", 110),
      {
        field: "current_interest_rate",
        headerName: "Rate",
        width: 72,
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
        headerName: "Documentation",
        flex: 1.2,
        minWidth: 120,
      },
      { field: "property_type", headerName: "Property", width: 100 },
      { field: "occupancy", headerName: "Occupancy", width: 100 },
      { field: "loan_purpose", headerName: "Purpose", width: 100 },
      intCol("remaining_term", "Rem term", 88),
      {
        field: "refinance_incentive",
        headerName: "Refi",
        width: 72,
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
      { field: "cohort", headerName: "Cohort", flex: 1.4, minWidth: 160 },
      {
        field: "has_mi",
        headerName: "Has MI",
        width: 80,
        valueFormatter: (p) =>
          p.value === true ? "true" : p.value === false ? "false" : "",
      },
    ],
    []
  );

  const assumptionColumnDefs = useMemo(
    () => [
      {
        field: "assumption_id",
        headerName: "ID",
        width: 200,
        cellClass: "cf-id",
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
        headerName: "Applies to",
        flex: 1,
        minWidth: 140,
      },
      {
        field: "related_data_path",
        headerName: "Data path",
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
      { field: "check_id", headerName: "Check", width: 160, cellClass: "cf-id" },
      { field: "source", headerName: "Source", width: 110 },
      intCol("edit_number", "Edit", 64),
      {
        field: "nl_description",
        headerName: "Description",
        flex: 2,
        minWidth: 200,
      },
      {
        field: "outcome",
        headerName: "Outcome",
        width: 88,
        cellClass: (p) => {
          if (p.value === "pass") return "qc-outcome-pass";
          if (p.value === "fail") return "qc-outcome-fail";
          if (p.value === "skipped") return "qc-outcome-skip";
          return "";
        },
      },
      intCol("fail_count", "Fails", 72),
      intCol("pass_count", "Passes", 80),
      {
        field: "detail",
        headerName: "Detail",
        flex: 1.2,
        minWidth: 140,
      },
    ],
    []
  );

  const stratColumnDefs = useMemo(
    () => [
      {
        field: "dimension",
        headerName: "Dimension",
        width: 130,
        cellClass: "cf-id",
      },
      { field: "bucket", headerName: "Bucket", flex: 1.4, minWidth: 140 },
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
        headerName: "Avg rate",
        width: 88,
        valueFormatter: (p) => fmtPct(p.value, 2),
        cellClass: "cf-num",
      },
      {
        field: "avg_refi_incentive",
        headerName: "Avg refi",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
    ],
    []
  );

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
        headerName: "Avg rate",
        width: 88,
        valueFormatter: (p) => fmtPct(p.value, 2),
        cellClass: "cf-num",
      },
      {
        field: "avg_refi_incentive",
        headerName: "Avg refi",
        width: 88,
        valueFormatter: (p) => fmtNum(p.value, 3),
        cellClass: "cf-num",
      },
      {
        field: "avg_remaining_term",
        headerName: "Avg rem",
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
      intCol("remainingTerm", "Remaining term", 110),
      {
        field: "refinanceIncentive",
        headerName: "Refi incentive",
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
      { field: "scenario_id", headerName: "ID", width: 64, cellClass: "cf-id" },
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
      intCol("recovery_period_months", "Rec mos", 80),
      intCol("recovery_lag_months", "Lag fallback", 96),
      intCol("avg_used_recovery_lag_months", "Avg used lag", 100),
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
      { field: "scenario_id", headerName: "ID", width: 72, cellClass: "cf-id" },
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
      moneyCol("beginning_balance", "Begin bal", 110),
      moneyCol("interest", "Interest", 100),
      moneyCol("scheduled_principal", "Sched prin", 100),
      moneyCol("default_amt", "New default", 100),
      moneyCol("default", "New default", 100),
      moneyCol("new_default", "New default", 100),
      moneyCol("prepay", "Prepay", 90),
      moneyCol("liquidated_default", "Liq default", 100),
      moneyCol("recovery", "Recovery", 90),
      moneyCol("realized_loss", "Realized loss", 100),
      moneyCol("total_cash", "Total cash", 100),
      moneyCol("ending_balance", "End UPB", 110),
      intCol("avg_used_recovery_lag_months", "Avg used lag", 100),
    ],
    []
  );

  const cfMonth1ColumnDefs = useMemo(
    () => [
      { field: "loan_id", headerName: "Loan", width: 100, cellClass: "cf-id" },
      { field: "scenario_id", headerName: "ID", width: 64, cellClass: "cf-id" },
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
      intCol("used_recovery_lag_months", "Used lag", 80),
      {
        headerName: "1 · Performing UPB",
        children: [
          intCol("month", "Mo", 56),
          moneyCol("beginning_balance", "Beg UPB", 110),
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched prin", 100),
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
          moneyCol("new_default", "New default", 100),
          moneyCol("default_amt", "New default", 100),
          moneyCol("ending_balance", "End UPB", 110),
        ],
      },
      {
        headerName: "2 · Default roll",
        children: [
          moneyCol("beginning_default_balance", "Beg def bal", 110),
          moneyCol("liquidated_default", "Liq default", 100),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("realized_loss", "Realized loss", 100),
          moneyCol("ending_default_balance", "End def bal", 110),
        ],
      },
      {
        headerName: "3 · Actual cash (defaults ≠ cash)",
        children: [
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched prin", 100),
          moneyCol("prepay", "Prepay", 90),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("total_cash", "Total cash", 100),
        ],
      },
    ],
    []
  );

  const loanMonthColumnDefs = useMemo(
    () => [
      { field: "scenario_id", headerName: "ID", width: 64, cellClass: "cf-id" },
      { field: "loan_id", headerName: "Loan", width: 100, cellClass: "cf-id" },
      intCol("used_recovery_lag_months", "Used lag", 80),
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
          moneyCol("scheduled_principal", "Sched prin", 100),
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
          moneyCol("new_default", "New default", 100),
          moneyCol("default_amt", "New default", 100),
          moneyCol("ending_balance", "End UPB", 110),
        ],
      },
      {
        headerName: "2 · Default roll",
        children: [
          moneyCol("beginning_default_balance", "Beg def bal", 110),
          moneyCol("liquidated_default", "Liq default", 100),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("realized_loss", "Realized loss", 100),
          moneyCol("loss", "Loss", 90),
          moneyCol("ending_default_balance", "End def bal", 110),
        ],
      },
      {
        headerName: "3 · Actual cash (defaults ≠ cash)",
        children: [
          moneyCol("interest", "Interest", 100),
          moneyCol("scheduled_principal", "Sched prin", 100),
          moneyCol("prepay", "Prepay", 90),
          moneyCol("recovery", "Recovery", 90),
          moneyCol("total_cash", "Total cash", 100),
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
    crumbs.push({ id: "agg", label: "CF aggregates", jumpable: cfView !== "agg" });
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
        label: "All loans · month 1",
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
    clusterFilter === "all" ? "All cohorts" : clusterFilter;

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
        <span className="topbar-version">v0.3.0</span>
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
          {pane === "asf" && (
            <section className="section section-fill">
              <div className="section-head">
                <h2 className="section-title">ASF Tape</h2>
                <p className="section-meta">
                  {asfSource || "asf_tape"}
                  {asfTotal ? ` · ${asfTotal} loans` : ""}
                  {" · all loans"}
                </p>
              </div>
              {asfLoading ? (
                <p className="muted">Loading ASF tape…</p>
              ) : asfError ? (
                <StatusBanner tone="error">ASF: {asfError}</StatusBanner>
              ) : (
                <DataGrid
                  rowData={asfLoans}
                  columnDefs={asfColumnDefs}
                  getRowId={(p) => String(p.data.loan_id)}
                  onRowDrill={drillLoan}
                  heightClass="grid-wrap-fill"
                  exportName="asf-tape"
                />
              )}
            </section>
          )}

          {pane === "qc" && (
            <section className="section section-fill">
              <div className="section-head">
                <h2 className="section-title">Loan Quality QC</h2>
                <p className="section-meta">
                  Neon asf_tape
                  {qcMeta?.tape_row_count != null
                    ? ` · ${qcMeta.tape_row_count} loans`
                    : ""}
                  {qcMeta?.run_id ? ` · run ${qcMeta.run_id}` : ""}
                  {qcMeta?.n != null ? ` · ${qcMeta.n} checks` : ""}
                </p>
              </div>
              {!qcLoading && !qcError && qcRows.length > 0 && (
                <div className="qc-summary">
                  <span className="qc-stat qc-stat-pass">
                    Pass {qcSummary.pass}
                  </span>
                  <span className="qc-stat qc-stat-fail">
                    Fail {qcSummary.fail}
                  </span>
                  <span className="qc-stat">Skip {qcSummary.skipped}</span>
                  <span className="qc-stat">
                    % pass{" "}
                    {qcSummary.pct == null
                      ? "—"
                      : `${qcSummary.pct.toFixed(1)}%`}
                  </span>
                </div>
              )}
              {qcLoading ? (
                <p className="muted">Loading QC results…</p>
              ) : qcError ? (
                <StatusBanner tone="error">QC: {qcError}</StatusBanner>
              ) : !qcRows.length ? (
                <p className="muted">
                  No QC results yet. Load asf_tape and run QC against Neon.
                </p>
              ) : (
                <DataGrid
                  rowData={qcRows}
                  columnDefs={qcColumnDefs}
                  getRowId={(p) => String(p.data.check_id)}
                  heightClass="grid-wrap-fill"
                  exportName="loan-qc"
                />
              )}
            </section>
          )}

          {pane === "strat" && (
            <section className="section section-fill">
              <div className="section-head">
                <h2 className="section-title">Stratification</h2>
                <div className="section-actions">
                  <p className="section-meta">
                    All alternate tape cuts (not K-prototype)
                    {stratMeta?.n_dimensions != null
                      ? ` · ${stratMeta.n_dimensions} dimensions`
                      : ""}
                    {stratMeta?.n_buckets != null
                      ? ` · ${stratMeta.n_buckets} buckets`
                      : ""}
                    {stratMeta?.tape_row_count != null
                      ? ` · ${stratMeta.tape_row_count} loans`
                      : ""}
                    {stratMeta?.tape_upb != null
                      ? ` · UPB ${Number(stratMeta.tape_upb).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                      : ""}
                  </p>
                </div>
              </div>
              {stratLoading ? (
                <p className="muted">Loading stratification…</p>
              ) : stratError ? (
                <StatusBanner tone="error">Strat: {stratError}</StatusBanner>
              ) : (
                <DataGrid
                  rowData={stratRows}
                  columnDefs={stratColumnDefs}
                  getRowId={(p) => String(p.data.row_key)}
                  heightClass="grid-wrap-fill"
                  exportName="stratification"
                />
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
                  <p className="scatter-subtitle">
                    Cohorts: high LTV + strong / high LTV + weak / low LTV +
                    weak refinance incentive
                  </p>
                </div>
                <div className="chart-wrap chart-wrap-scatter">
                  {tapeLoading ? (
                    <p className="muted">Loading tape…</p>
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
                  <h2 className="section-title">Cohort statistics</h2>
                  <p className="section-meta">
                    Per-cohort count · UPB · avg LTV/CLTV/FICO
                  </p>
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
                      Ran scenarios: {ranScenarioIds.length}/27
                      {" · "}
                      Click row → cohort scenarios
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
                <h2 className="section-title">Cash Flow Scenarios</h2>
                <div className="section-actions">
                  <p className="section-meta">
                    Neon securitization_scenarios
                    {selectedCohort
                      ? ` · cohort filter: ${selectedCohort}`
                      : " · 27 cells"}
                    {" · "}
                    Scenario col merges PSA×SDA across cohorts
                    {" · "}
                    Click row → all-loan month-1 CF
                  </p>
                  {(selectedCohort || selectedLoanId) && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={clearDrill}
                    >
                      Clear drill
                    </button>
                  )}
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
                <h2 className="section-title">
                  {cfView === "loanMonth"
                    ? "Cash Flow · multi-month"
                    : cfView === "month1"
                      ? "Cash Flow · all loans · month 1"
                      : "Cash Flow · scenario aggregates"}
                </h2>
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
                    All loans
                  </button>
                  {cfView === "loanMonth" && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => setCfView("month1")}
                    >
                      Back to loans
                    </button>
                  )}
                  {(selectedLoanId || selectedCohort) && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={clearDrill}
                    >
                      Clear drill
                    </button>
                  )}
                </div>
              </div>
              <DrillTrail crumbs={drillCrumbs} onJump={onDrillJump} />
              <p className="section-meta">
                {cfView === "loanMonth"
                  ? `Neon loan_month_cf_enriched · ${selectedLoanId} · ${selectedScenarioId}`
                  : cfView === "month1"
                    ? `Neon loan_cashflows_month1_enriched · ${selectedScenarioId}${
                        neonMonth1Total ? ` · ${neonMonth1Total} loans` : ""
                      } · click row → months`
                    : `Scenario aggregates (all loans) · ${aggregates.length || 0} cells · click → loan-level`}
              </p>
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
                <h2 className="section-title">Assumptions</h2>
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
                <p className="muted">Loading assumptions…</p>
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
