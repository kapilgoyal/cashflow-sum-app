/**
 * 27-scenario total cashflow chart (Scenarios pane).
 * Prefers GET /api/cashflows/scenario-grid; falls back to /scenario-grid-cashflow.json.
 */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiUrl } from "./apiBase";
import { FONT } from "./cashflowGrid";
import {
  CLUSTER_COLORS,
  CLUSTER_ORDER,
  cohortLabel,
} from "./cohortLabels";

const SCENARIO_IDS = Array.from(
  { length: 27 },
  (_, i) => `S${String(i + 1).padStart(2, "0")}`
);

function moneyTick(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  const abs = Math.abs(n);
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function tipStyle() {
  return {
    background: "#0C0C0C",
    border: "1px solid #323232",
    borderRadius: 0,
    fontSize: 11,
    color: "#FCFCFC",
    fontFamily: FONT,
  };
}

/** Normalize scenarios meta: object keyed by id, or array of rows. */
function normalizeScenariosMeta(raw) {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    const out = {};
    for (const row of raw) {
      const id = row?.scenario_id || row?.id;
      if (!id) continue;
      out[id] = {
        ...row,
        cohort: cohortLabel(row.cohort),
      };
    }
    return out;
  }
  if (typeof raw === "object") {
    return Object.fromEntries(
      Object.entries(raw).map(([id, row]) => [
        id,
        row && typeof row === "object"
          ? { ...row, cohort: cohortLabel(row.cohort) }
          : row,
      ])
    );
  }
  return {};
}

/** Flatten month rows so each S01…S27 is a top-level numeric key. */
function normalizeMonthRows(rows) {
  if (!Array.isArray(rows) || !rows.length) return [];
  return rows.map((row) => {
    const out = { month: Number(row.month ?? row.t ?? row.Month) };
    const nested = row.scenarios || row.cash || row.values;
    if (nested && typeof nested === "object" && !Array.isArray(nested)) {
      for (const id of SCENARIO_IDS) {
        const v = nested[id];
        if (v != null && Number.isFinite(Number(v))) out[id] = Number(v);
      }
    }
    for (const id of SCENARIO_IDS) {
      if (out[id] != null) continue;
      const v = row[id];
      if (v != null && Number.isFinite(Number(v))) out[id] = Number(v);
    }
    return out;
  });
}

function defaultCohortForId(id) {
  const n = Number(String(id).replace(/^S/i, ""));
  if (!Number.isFinite(n)) return null;
  if (n >= 1 && n <= 9) return CLUSTER_ORDER[0];
  if (n >= 10 && n <= 18) return CLUSTER_ORDER[1];
  if (n >= 19 && n <= 27) return CLUSTER_ORDER[2];
  return null;
}

export default function ScenarioGridCashCharts() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        let res = await fetch(apiUrl("/api/cashflows/scenario-grid")).catch(
          () => null
        );
        if (!res || !res.ok) {
          res = await fetch("/scenario-grid-cashflow.json").catch(() => null);
        }
        if (!res || !res.ok) {
          throw new Error("27-scenario cashflow not loaded yet");
        }
        const data = await res.json();
        if (!cancelled) setPayload(data);
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

  const scenariosMeta = useMemo(
    () => normalizeScenariosMeta(payload?.scenarios || payload?.meta?.scenarios),
    [payload]
  );

  const series = useMemo(() => {
    return SCENARIO_IDS.map((id) => {
      const meta = scenariosMeta[id] || {};
      const cohort =
        cohortLabel(meta.cohort) || defaultCohortForId(id) || CLUSTER_ORDER[0];
      return {
        key: id,
        cohort,
        color: CLUSTER_COLORS[cohort] || "#808080",
        psa: meta.psa_multiple,
        sda: meta.sda_multiple,
      };
    });
  }, [scenariosMeta]);

  const data = useMemo(() => {
    const rows = normalizeMonthRows(payload?.months || []);
    if (!rows.length) return [];
    let last = rows.length - 1;
    while (last > 0) {
      const row = rows[last];
      const any = SCENARIO_IDS.some((id) => Number(row?.[id]) > 0.5);
      if (any) break;
      last -= 1;
    }
    return rows.slice(0, last + 1);
  }, [payload]);

  const horizon = data.length
    ? data[data.length - 1].month
    : payload?.horizon_months || 360;

  const metaBits = useMemo(() => {
    const nPresent = series.filter((s) =>
      data.some((row) => Number(row[s.key]) > 0)
    ).length;
    const bits = [];
    if (nPresent) bits.push(`${nPresent} paths`);
    if (horizon) bits.push(`cash thru mo ${horizon}`);
    return bits.join(" · ");
  }, [series, data, horizon]);

  return (
    <div
      className="scenario-cash-panel scenario-grid-cash-panel scenario-component-chart"
      aria-label="27 Scenario Total Cash"
    >
      <div className="scenario-cash-head">
        <h3 className="scenario-cash-title scenario-section-title">
          27 Scenarios
        </h3>
        <p className="scenario-component-stat">
          {loading
            ? "…"
            : error
              ? error
              : metaBits || "S01–S27"}
        </p>
      </div>

      <div className="scenario-component-chart-body scenario-grid-cash-chart">
        {loading ? (
          <p className="muted strat-chart-empty">Calculating…</p>
        ) : error || !data.length ? (
          <p className="muted strat-chart-empty">
            {error || "No 27-Scenario Cashflow Yet."}
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minHeight={90}>
            <LineChart
              data={data}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                stroke="#323232"
                strokeDasharray="2 4"
                strokeOpacity={0.9}
              />
              <XAxis
                dataKey="month"
                type="number"
                domain={[1, horizon]}
                ticks={[1, 60, 120, 180, 240, horizon]
                  .filter((t) => t <= horizon)
                  .filter((t, i, a) => a.indexOf(t) === i)}
                tick={{ fill: "#808080", fontSize: 8, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
              />
              <YAxis
                tickFormatter={moneyTick}
                width={44}
                tickCount={4}
                tick={{ fill: "#808080", fontSize: 8, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
                domain={[0, "auto"]}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#808080" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={(v, name) => {
                  const s = series.find((x) => x.key === name);
                  const tag = s
                    ? `${name} · ${s.cohort}${
                        s.psa != null ? ` PSA${s.psa}` : ""
                      }${s.sda != null ? `/SDA${s.sda}` : ""}`
                    : name;
                  return [moneyTick(v), tag];
                }}
                itemSorter={(item) => -Number(item.value || 0)}
              />
              {series.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.key}
                  stroke={s.color}
                  strokeWidth={1}
                  strokeOpacity={0.85}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
