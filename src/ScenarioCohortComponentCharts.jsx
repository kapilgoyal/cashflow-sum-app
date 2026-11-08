/**
 * Cohort-AVG cashflow component charts (Interest / Sched / Prepay / New Default / Recovery).
 * Data: cohort_avg[cohort].months[*] from scenario-grid JSON/API; Pool = sum of 3 cohorts.
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
import { FONT, chartMoney } from "./cashflowGrid";
import {
  CLUSTER_COLORS,
  CLUSTER_ORDER,
  cohortLabel,
} from "./cohortLabels";

const POOL_COLOR = "#fd9d24";

const COMPONENTS = [
  {
    field: "interest",
    title: "Interest · Cohort Avg",
    yLabel: "Interest",
  },
  {
    field: "scheduled_principal",
    title: "Scheduled Principal · Cohort Avg",
    yLabel: "Sched Prin",
  },
  {
    field: "prepay",
    title: "Unscheduled Principal (Prepay) · Cohort Avg",
    yLabel: "Prepay",
  },
  {
    field: "new_default",
    title: "New Default · Cohort Avg",
    yLabel: "New Default",
    note: "Not cash — default inventory inflow",
  },
  {
    field: "recovery",
    title: "Recovery Principal · Cohort Avg",
    yLabel: "Recovery",
  },
];

function moneyTick(v) {
  return chartMoney(v);
}

function poolFieldStats(data, field) {
  let m1 = 0;
  let peak = 0;
  let sum = 0;
  for (const row of data) {
    const v = Number(row[`${field}__Pool`] || 0);
    if (!Number.isFinite(v)) continue;
    if (Number(row.month) === 1) m1 = v;
    if (v > peak) peak = v;
    sum += v;
  }
  return { m1, peak, sum };
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

function buildSeriesRows(cohortAvg) {
  if (!cohortAvg || typeof cohortAvg !== "object") return [];
  const byCohort = {};
  let maxM = 0;
  for (const c of CLUSTER_ORDER) {
    const cell = cohortAvg[c] || cohortAvg[cohortLabel(c)];
    const months = cell?.months || [];
    const map = new Map();
    for (const row of months) {
      const m = Number(row.month);
      if (!Number.isFinite(m)) continue;
      map.set(m, row);
      if (m > maxM) maxM = m;
    }
    byCohort[c] = map;
  }
  if (!maxM) return [];

  const rows = [];
  for (let m = 1; m <= maxM; m += 1) {
    const out = { month: m };
    let poolAny = 0;
    for (const c of CLUSTER_ORDER) {
      const row = byCohort[c]?.get(m) || {};
      for (const comp of COMPONENTS) {
        const key = `${comp.field}__${c}`;
        const v = Number(row[comp.field] || 0);
        out[key] = v;
        const poolKey = `${comp.field}__Pool`;
        out[poolKey] = (out[poolKey] || 0) + v;
        poolAny += Math.abs(v);
      }
    }
    rows.push(out);
    // keep trailing zeros until trim pass
    void poolAny;
  }

  // Trim trailing months where every component×cohort is ~0
  let last = rows.length - 1;
  while (last > 0) {
    const row = rows[last];
    const any = COMPONENTS.some((comp) =>
      CLUSTER_ORDER.some(
        (c) => Math.abs(Number(row[`${comp.field}__${c}`] || 0)) > 0.5
      )
    );
    if (any) break;
    last -= 1;
  }
  return rows.slice(0, last + 1);
}

function ComponentChart({ config, data, horizon, loading, error }) {
  const series = useMemo(
    () =>
      CLUSTER_ORDER.map((c) => ({
        key: `${config.field}__${c}`,
        label: cohortLabel(c),
        color: CLUSTER_COLORS[c],
      })),
    [config.field]
  );

  const stats = useMemo(
    () => poolFieldStats(data, config.field),
    [data, config.field]
  );

  const shortTitle = config.yLabel;

  return (
    <div
      className="scenario-component-chart"
      aria-label={config.title}
    >
      <div className="scenario-cash-head">
        <h4
          className="scenario-cash-title scenario-component-title"
          title={config.note || config.title}
        >
          {shortTitle}
        </h4>
        <p className="scenario-component-stat" title="Pool month-1 · peak">
          {loading
            ? "…"
            : data.length
              ? `M1 ${moneyTick(stats.m1)} · Pk ${moneyTick(stats.peak)}`
              : "—"}
        </p>
      </div>
      <div className="scenario-component-chart-body">
        {loading ? (
          <p className="muted strat-chart-empty">Calculating…</p>
        ) : error || !data.length ? (
          <p className="muted strat-chart-empty">
            {error || "No Cohort-Avg Components Yet."}
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minHeight={90}>
            <LineChart
              data={data}
              margin={{ top: 2, right: 4, left: 0, bottom: 0 }}
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
                width={48}
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
                formatter={(v, name) => [moneyTick(v), name]}
              />
              {series.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={1.25}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
              <Line
                type="monotone"
                dataKey={`${config.field}__Pool`}
                name="Pool"
                stroke={POOL_COLOR}
                strokeWidth={1.1}
                strokeDasharray="4 3"
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default function ScenarioCohortComponentCharts() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const { fetchScenarioGridCf } = await import("./cfCache");
        const data = await fetchScenarioGridCf();
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

  const data = useMemo(
    () => buildSeriesRows(payload?.cohort_avg),
    [payload]
  );
  const horizon = data.length
    ? data[data.length - 1].month
    : payload?.horizon_months || 360;

  const hasComponents = useMemo(() => {
    if (!data.length) return false;
    const row = data[0];
    return COMPONENTS.every((c) =>
      CLUSTER_ORDER.some((co) => row[`${c.field}__${co}`] != null)
    );
  }, [data]);

  return (
    <div
      className="scenario-component-panel"
      aria-label="Cohort Avg Cashflow Components"
    >
      <div className="scenario-cash-head scenario-section-head">
        <h3 className="scenario-cash-title scenario-section-title">
          Components
        </h3>
        <p className="scenario-component-stat">
          {loading
            ? "…"
            : error
              ? error
              : !hasComponents && data.length
                ? "Re-run CF for fields"
                : horizon
                  ? `9-cell mean · mo ${horizon}`
                  : "9-cell mean"}
        </p>
      </div>
      <div className="scenario-component-grid">
        {COMPONENTS.map((config) => (
          <ComponentChart
            key={config.field}
            config={config}
            data={data}
            horizon={horizon}
            loading={loading}
            error={error}
          />
        ))}
      </div>
    </div>
  );
}
