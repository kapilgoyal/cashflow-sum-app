/**
 * Bottom Scenarios band: 27-scenario total cash + pool Avg vs Stress (+ cum prin).
 * Loads GET /api/cashflows/scenario-grid only (CF-191: no static JSON bypass).
 *
 * Avg  = Σ of 3 cohort 9-cell means (cohort_avg) — not min of paths.
 * Stress = Σ PSA Down / SDA Up cells (typically S03+S12+S21).
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

const SCENARIO_IDS = Array.from(
  { length: 27 },
  (_, i) => `S${String(i + 1).padStart(2, "0")}`
);

const AVG_COLOR = "#fd9d24";
const STRESS_COLOR = "#c51d46";
const TICK = { fill: "#808080", fontSize: 8, fontFamily: FONT };
const AXIS = { stroke: "#464646" };

function moneyTick(v) {
  return chartMoney(v);
}

function tipStyle() {
  return {
    background: "#0C0C0C",
    border: "1px solid #323232",
    borderRadius: 0,
    fontSize: 11,
    color: "#FCFCFC",
    fontFamily: FONT,
    boxShadow: "none",
  };
}

function normalizeScenariosMeta(raw) {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    const out = {};
    for (const row of raw) {
      const id = row?.scenario_id || row?.id;
      if (!id) continue;
      out[id] = { ...row, cohort: cohortLabel(row.cohort) };
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

function normalizeMonthRows(rows) {
  if (!Array.isArray(rows) || !rows.length) return [];
  return rows.map((row) => {
    const out = { month: Number(row.month ?? row.t ?? row.Month) };
    const nested = row.scenarios || row.cash || row.values;
    if (nested && typeof nested === "object" && !Array.isArray(nested)) {
      for (const id of SCENARIO_IDS) {
        const v = nested[id];
        if (v != null && Number.isFinite(Number(v))) out[id] = Number(v);
        const p = nested[`${id}__prin`];
        if (p != null && Number.isFinite(Number(p))) out[`${id}__prin`] = Number(p);
      }
    }
    for (const id of SCENARIO_IDS) {
      if (out[id] == null) {
        const v = row[id];
        if (v != null && Number.isFinite(Number(v))) out[id] = Number(v);
      }
      const pk = `${id}__prin`;
      if (out[pk] == null) {
        const p = row[pk];
        if (p != null && Number.isFinite(Number(p))) out[pk] = Number(p);
      }
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

function trimTrailing(rows, valueKeys) {
  if (!rows.length) return rows;
  let last = rows.length - 1;
  while (last > 0) {
    const row = rows[last];
    const any = valueKeys.some((k) => Number(row?.[k]) > 0.5);
    if (any) break;
    last -= 1;
  }
  return rows.slice(0, last + 1);
}

function trimCumRows(rows, keys) {
  if (!rows.length) return rows;
  let last = rows.length - 1;
  while (last > 1) {
    const delta = keys.reduce(
      (acc, k) =>
        acc +
        (Number(rows[last][k] || 0) - Number(rows[last - 1][k] || 0)),
      0
    );
    if (delta > 0.5) break;
    last -= 1;
  }
  return rows.slice(0, last + 1);
}

/** PSA Down + SDA Up — labeled speeds only (not min of cash paths). */
function pickStressIds(scenariosMeta) {
  const labeled = SCENARIO_IDS.filter((id) => {
    const m = scenariosMeta[id];
    return m?.pca_level === "Down" && m?.sta_level === "Up";
  });
  if (labeled.length) return labeled;

  const psas = SCENARIO_IDS.map((id) => Number(scenariosMeta[id]?.psa_multiple)).filter(
    Number.isFinite
  );
  const sdas = SCENARIO_IDS.map((id) => Number(scenariosMeta[id]?.sda_multiple)).filter(
    Number.isFinite
  );
  if (!psas.length || !sdas.length) return [];
  const minPsa = Math.min(...psas);
  const maxSda = Math.max(...sdas);
  return SCENARIO_IDS.filter((id) => {
    const m = scenariosMeta[id];
    return (
      Number(m?.psa_multiple) === minPsa && Number(m?.sda_multiple) === maxSda
    );
  });
}

function avgLabel(avg, c) {
  return avg?.[c] || avg?.[cohortLabel(c)];
}

function buildPoolFieldByMonth(cohortAvg, field) {
  if (!cohortAvg || typeof cohortAvg !== "object") return new Map();
  const maps = {};
  let maxM = 0;
  for (const c of CLUSTER_ORDER) {
    const cell = avgLabel(cohortAvg, c);
    const map = new Map();
    for (const row of cell?.months || []) {
      const m = Number(row.month);
      if (!Number.isFinite(m)) continue;
      let v = Number(row[field] || 0);
      if (!v && field === "principal_cash") {
        v =
          Number(row.scheduled_principal || 0) +
          Number(row.prepay || 0) +
          Number(row.recovery || 0);
      }
      map.set(m, v);
      if (m > maxM) maxM = m;
    }
    maps[c] = map;
  }
  const out = new Map();
  for (let m = 1; m <= maxM; m += 1) {
    let sum = 0;
    for (const c of CLUSTER_ORDER) sum += Number(maps[c]?.get(m) || 0);
    out.set(m, sum);
  }
  return out;
}

function ChartPanel({
  title,
  titleTip,
  stat,
  loading,
  error,
  empty,
  data,
  horizon,
  lines,
  tipFormatter,
}) {
  const ticks = [1, 60, 120, 180, 240, horizon]
    .filter((t) => t <= horizon)
    .filter((t, i, a) => a.indexOf(t) === i);

  return (
    <div
      className="scenario-cash-panel scenario-grid-cash-panel scenario-component-chart"
      aria-label={title}
    >
      <div className="scenario-cash-head">
        <h3
          className="scenario-cash-title scenario-section-title"
          title={titleTip || title}
        >
          {title}
        </h3>
        <p className="scenario-component-stat">{loading ? "…" : error ? error : stat}</p>
      </div>
      <div className="scenario-component-chart-body scenario-grid-cash-chart">
        {loading ? (
          <p className="muted strat-chart-empty">Calculating…</p>
        ) : error || !data.length ? (
          <p className="muted strat-chart-empty">{empty || error || "No Data."}</p>
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
                ticks={ticks}
                tick={TICK}
                axisLine={AXIS}
                tickLine={AXIS}
              />
              <YAxis
                tickFormatter={moneyTick}
                width={48}
                tickCount={4}
                tick={TICK}
                axisLine={AXIS}
                tickLine={AXIS}
                domain={[0, "auto"]}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#808080" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={
                  tipFormatter || ((v, name) => [moneyTick(v), name])
                }
                itemSorter={(item) => -Number(item.value || 0)}
              />
              {lines.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name || s.key}
                  stroke={s.color}
                  strokeWidth={s.width ?? 1.25}
                  strokeOpacity={s.opacity ?? 0.9}
                  strokeDasharray={s.dash}
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
        // CF-191: API fingerprint gate only — no static JSON bypass.
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

  const scenariosMeta = useMemo(
    () => normalizeScenariosMeta(payload?.scenarios || payload?.meta?.scenarios),
    [payload]
  );

  const series27 = useMemo(() => {
    return SCENARIO_IDS.map((id) => {
      const meta = scenariosMeta[id] || {};
      const cohort =
        cohortLabel(meta.cohort) || defaultCohortForId(id) || CLUSTER_ORDER[0];
      return {
        key: id,
        name: id,
        cohort,
        color: CLUSTER_COLORS[cohort] || "#808080",
        psa: meta.psa_multiple,
        sda: meta.sda_multiple,
        width: 1,
        opacity: 0.85,
      };
    });
  }, [scenariosMeta]);

  const monthRows = useMemo(
    () => normalizeMonthRows(payload?.months || []),
    [payload]
  );

  const data27 = useMemo(
    () => trimTrailing(monthRows, SCENARIO_IDS),
    [monthRows]
  );

  const stressIds = useMemo(
    () => pickStressIds(scenariosMeta),
    [scenariosMeta]
  );

  const avgStressCash = useMemo(() => {
    const avgByM = buildPoolFieldByMonth(payload?.cohort_avg, "total_cash");
    if (!avgByM.size && !monthRows.length) return [];
    const maxM = Math.max(
      ...avgByM.keys(),
      ...monthRows.map((r) => Number(r.month)).filter(Number.isFinite),
      0
    );
    const byMonth = new Map(monthRows.map((r) => [Number(r.month), r]));
    const rows = [];
    for (let m = 1; m <= maxM; m += 1) {
      const wide = byMonth.get(m) || {};
      let stress = 0;
      for (const id of stressIds) stress += Number(wide[id] || 0);
      rows.push({
        month: m,
        Avg: Number(avgByM.get(m) || 0),
        Stress: stress,
      });
    }
    return trimTrailing(rows, ["Avg", "Stress"]);
  }, [payload, monthRows, stressIds]);

  const avgStressCumPrin = useMemo(() => {
    const avgPrin = buildPoolFieldByMonth(payload?.cohort_avg, "principal_cash");
    if (!avgPrin.size && !monthRows.length) {
      return { rows: [], hasStressPrin: false };
    }
    const byMonth = new Map(monthRows.map((r) => [Number(r.month), r]));
    const maxM = Math.max(
      ...avgPrin.keys(),
      ...monthRows.map((r) => Number(r.month)).filter(Number.isFinite),
      0
    );
    let hasStressPrin = false;
    let avgRun = 0;
    let stressRun = 0;
    const rows = [];
    for (let m = 1; m <= maxM; m += 1) {
      avgRun += Number(avgPrin.get(m) || 0);
      const wide = byMonth.get(m) || {};
      let stress = 0;
      for (const id of stressIds) {
        const p = Number(wide[`${id}__prin`]);
        if (Number.isFinite(p)) {
          hasStressPrin = true;
          stress += p;
        }
      }
      stressRun += stress;
      rows.push({ month: m, Avg: avgRun, Stress: stressRun });
    }
    return {
      rows: trimCumRows(rows, hasStressPrin ? ["Avg", "Stress"] : ["Avg"]),
      hasStressPrin,
    };
  }, [payload, monthRows, stressIds]);

  const horizon27 = data27.length
    ? data27[data27.length - 1].month
    : payload?.horizon_months || 360;
  const horizonCash = avgStressCash.length
    ? avgStressCash[avgStressCash.length - 1].month
    : horizon27;
  const horizonCum = avgStressCumPrin.rows.length
    ? avgStressCumPrin.rows[avgStressCumPrin.rows.length - 1].month
    : horizon27;

  const meta27 = useMemo(() => {
    const nPresent = series27.filter((s) =>
      data27.some((row) => Number(row[s.key]) > 0)
    ).length;
    const bits = [];
    if (nPresent) bits.push(`${nPresent} paths`);
    if (horizon27) bits.push(`cash thru mo ${horizon27}`);
    return bits.join(" · ");
  }, [series27, data27, horizon27]);

  const stressMeta = useMemo(() => {
    if (!stressIds.length) return "No stress cells";
    const sample = scenariosMeta[stressIds[0]] || {};
    const bits = [stressIds.join("+")];
    if (sample.psa_multiple != null && sample.sda_multiple != null) {
      bits.push(`PSA ${sample.psa_multiple} / SDA ${sample.sda_multiple}`);
    }
    bits.push("Down×Up");
    return bits.join(" · ");
  }, [stressIds, scenariosMeta]);

  const stressLines = [
    {
      key: "Stress",
      name: "Stress",
      color: STRESS_COLOR,
      width: 1.35,
    },
    {
      key: "Avg",
      name: "Avg",
      color: AVG_COLOR,
      width: 1.15,
      dash: "4 3",
    },
  ];

  const cumFinal = avgStressCumPrin.rows.length
    ? avgStressCumPrin.rows[avgStressCumPrin.rows.length - 1]
    : null;

  return (
    <div className="scenario-grid-cash-row" aria-label="Scenario Cash Paths">
      <ChartPanel
        title="27 Scenarios"
        titleTip="Monthly total cash · all 27 PSA×SDA×cohort cells"
        stat={meta27 || "S01–S27"}
        loading={loading}
        error={error}
        empty="No 27-Scenario Cashflow Yet."
        data={data27}
        horizon={horizon27}
        lines={series27}
        tipFormatter={(v, name) => {
          const s = series27.find((x) => x.key === name);
          const tag = s
            ? `${name} · ${s.cohort}${
                s.psa != null ? ` PSA${s.psa}` : ""
              }${s.sda != null ? `/SDA${s.sda}` : ""}`
            : name;
          return [moneyTick(v), tag];
        }}
      />
      <ChartPanel
        title="Avg Vs Stress"
        titleTip="Monthly total cash. Avg = Σ cohort 9-cell means. Stress = PSA↓/SDA↑ pool (not min of paths)."
        stat={stressMeta}
        loading={loading}
        error={error}
        empty="No Avg / Stress Series Yet."
        data={avgStressCash}
        horizon={horizonCash}
        lines={stressLines}
      />
      <ChartPanel
        title="Cum Prin · Avg Vs Stress"
        titleTip="Cumulative sched+prepay+recovery. Same Avg / Stress cells as total cash."
        stat={
          !avgStressCumPrin.hasStressPrin
            ? "Stress prin missing"
            : cumFinal
              ? `Σ Avg ${moneyTick(cumFinal.Avg)} · Stress ${moneyTick(
                  cumFinal.Stress
                )}`
              : stressMeta
        }
        loading={loading}
        error={error}
        empty="No Cum Prin Series Yet."
        data={avgStressCumPrin.rows}
        horizon={horizonCum}
        lines={stressLines}
      />
    </div>
  );
}
