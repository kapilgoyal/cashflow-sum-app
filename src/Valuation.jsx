/**
 * Valuation: FRED Treasury, QuantLib NPV / Z-spread risk.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiUrl } from "./apiBase";
import {
  FONT,
  PaneSpinner,
  fmtNum,
  fmtPct,
  fmtUpbShort,
  pushToast,
} from "./cashflowGrid";

const TICK = { fill: "#808080", fontSize: 9, fontFamily: FONT, fontWeight: 300 };
const AXIS = { stroke: "#464646" };
const AMBER = "#fd9d24";
const CURVE = "#5b9bd5";
const BAR = "#3d6a8a";
const GRID = "#2a2a2a";

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

function yieldTick(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  return `${n.toFixed(2)}%`;
}

function priceTick(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  return n.toFixed(2);
}

function fmtDollar(v) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtDelta(v) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) < 1e-9) return "—";
  return `${n > 0 ? "+" : ""}${fmtNum(n, 4)}`;
}

function Kpi({ label, children }) {
  return (
    <div className="qc-kpi" aria-label={label}>
      <span className="qc-kpi-label">{label}</span>
      <span className="qc-kpi-value">{children}</span>
    </div>
  );
}

function PctBar({ pct }) {
  const w = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <span className="valuation-pct-bar" title={`${fmtNum(w, 1)}%`}>
      <span className="valuation-pct-bar-fill" style={{ width: `${w}%` }} />
      <span className="valuation-pct-bar-label">{fmtNum(w, 0)}%</span>
    </span>
  );
}

export default function Valuation() {
  const [zInput, setZInput] = useState("100");
  const [zSpread, setZSpread] = useState(100);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyLabel, setBusyLabel] = useState("Loading Valuation…");

  const load = useCallback(async (zs, opts = {}) => {
    const {
      refreshFred = false,
      successToast = null,
      spinnerLabel = "Loading Valuation…",
    } = opts;
    setLoading(true);
    setBusyLabel(spinnerLabel);
    try {
      const q = new URLSearchParams({
        servicing_bp: "35",
        z_spread_bp: String(zs),
      });
      if (refreshFred) q.set("refresh_fred", "true");
      const res = await fetch(apiUrl(`/api/valuation?${q}`));
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      setPayload(data);
      setZSpread(Number(zs));
      setZInput(String(zs));
      if (successToast) pushToast(successToast, "info");
    } catch (err) {
      pushToast(`Valuation: ${err.message || String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(zSpread, { spinnerLabel: "Loading Valuation…" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const applyZ = useCallback(() => {
    const n = Number(zInput);
    if (!Number.isFinite(n) || n < -500 || n > 2000) {
      pushToast("Z-Spread must be between −500 and 2000 bp", "error");
      return;
    }
    load(n, {
      spinnerLabel: "Updating Valuation…",
      successToast: `Valuation updated · Z-Spread ${n} bp`,
    });
  }, [zInput, load]);

  const refreshCurve = useCallback(() => {
    load(zSpread, {
      refreshFred: true,
      spinnerLabel: "Refreshing Treasury Curve…",
      successToast: "Treasury curve refreshed",
    });
  }, [load, zSpread]);

  const curveData = useMemo(
    () =>
      (payload?.treasury?.points || []).map((p) => ({
        tenor: Number(p.tenor_years),
        yield_pct: Number(p.yield_pct),
        extrapolated: Boolean(p.extrapolated),
        series: p.series_id,
      })),
    [payload]
  );

  const scenarioMatrix = useMemo(() => {
    const rows = payload?.scenarios || [];
    const base = rows.find((s) => s.is_base);
    const basePx = base != null ? Number(base.price_pts) : null;
    const baseNpv = base != null ? Number(base.npv) : null;
    const cs01 = Number(payload?.cs01);
    return rows.map((s) => {
      const price = Number(s.price_pts);
      const npv = Number(s.npv);
      const offset = Number(s.offset_bp) || 0;
      // Linear CS01 P&L: widen Z → mark-to-market loss for a long position.
      const cs01Pnl =
        Number.isFinite(cs01) && !s.is_base ? -cs01 * offset : null;
      return {
        label: s.label,
        z: Number(s.z_spread_bp),
        price,
        delta:
          basePx != null && Number.isFinite(price) ? price - basePx : null,
        deltaNpv:
          baseNpv != null && Number.isFinite(npv) ? npv - baseNpv : null,
        cs01Pnl,
        isBase: Boolean(s.is_base),
      };
    });
  }, [payload]);

  const krdMatrix = useMemo(() => {
    const rows = payload?.key_rate_durations || [];
    const totalDur = rows.reduce(
      (s, k) => s + Math.abs(Number(k.duration) || 0),
      0
    );
    const totalDv01 = rows.reduce((s, k) => s + (Number(k.dv01) || 0), 0);
    const items = rows.map((k) => {
      const duration = Number(k.duration);
      return {
        label: k.label,
        duration,
        dv01: Number(k.dv01),
        pct: totalDur > 0 ? (Math.abs(duration) / totalDur) * 100 : 0,
      };
    });
    return { items, totalDur, totalDv01 };
  }, [payload]);

  const speeds = payload?.speeds || {};

  if (loading && !payload) {
    return (
      <section className="section section-fill section-valuation">
        <PaneSpinner label={busyLabel} />
      </section>
    );
  }

  return (
    <section
      className={`section section-fill section-valuation${
        loading ? " is-loading" : ""
      }`}
    >
      {loading && (
        <div className="valuation-spinner-overlay" aria-busy="true">
          <PaneSpinner label={busyLabel} />
        </div>
      )}

      <div className="valuation-toolbar">
        <label className="valuation-z-field">
          <span className="valuation-z-label">Z-Spread (bp)</span>
          <input
            type="number"
            className="valuation-z-input"
            value={zInput}
            step="1"
            min={-500}
            max={2000}
            disabled={loading}
            onChange={(e) => setZInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") applyZ();
            }}
          />
        </label>
        <button
          type="button"
          className="valuation-btn"
          onClick={applyZ}
          disabled={loading}
        >
          Apply
        </button>
        <button
          type="button"
          className="valuation-btn valuation-btn-ghost"
          onClick={refreshCurve}
          disabled={loading}
        >
          {loading ? "Working…" : "Refresh Curve"}
        </button>
        <span className="valuation-meta">
          Servicing {fmtNum(payload?.servicing_bp ?? 35, 0)} bp
          {payload?.treasury?.as_of
            ? ` · Treasury ${payload.treasury.as_of}`
            : ""}
          {payload?.start_upb != null
            ? ` · UPB ${fmtUpbShort(payload.start_upb)}`
            : ""}
        </span>
      </div>

      <div className="qc-kpi-strip valuation-kpi-strip" aria-label="Valuation KPIs">
        <Kpi label="Price">
          {payload?.price_pts != null ? fmtNum(payload.price_pts, 2) : "—"}
        </Kpi>
        <Kpi label="WAL">
          {payload?.wal_years != null
            ? `${fmtNum(payload.wal_years, 2)} yr`
            : "—"}
        </Kpi>
        <Kpi label="Duration">
          {payload?.duration != null
            ? `${fmtNum(payload.duration, 2)} yr`
            : "—"}
        </Kpi>
        <Kpi label="CS01">{fmtDollar(payload?.cs01)}</Kpi>
        <Kpi label="DV01">{fmtDollar(payload?.dv01)}</Kpi>
        <Kpi label="Convexity">{fmtDollar(payload?.convexity_dollar)}</Kpi>
        <Kpi label="CPR">
          {speeds.cpr != null ? fmtPct(speeds.cpr, 1) : "—"}
        </Kpi>
        <Kpi label="CDR">
          {speeds.cdr != null ? fmtPct(speeds.cdr, 1) : "—"}
        </Kpi>
        <Kpi label="CRR">
          {speeds.crr != null ? fmtPct(speeds.crr, 1) : "—"}
        </Kpi>
      </div>

      <div className="valuation-body">
        <div className="valuation-charts">
          <div className="valuation-panel">
            <div className="valuation-panel-head">
              <h2 className="valuation-panel-title">Treasury Curve</h2>
              <span className="valuation-panel-sub">FRED CMT</span>
            </div>
            <div className="valuation-chart-wrap">
              {curveData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={curveData}
                    margin={{ top: 6, right: 10, left: 0, bottom: 2 }}
                  >
                    <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
                    <XAxis
                      dataKey="tenor"
                      type="number"
                      domain={[0, 40]}
                      ticks={[2, 5, 10, 20, 30, 40]}
                      tick={TICK}
                      axisLine={AXIS}
                      tickLine={AXIS}
                      tickFormatter={(v) => `${v}Y`}
                    />
                    <YAxis
                      width={40}
                      tick={TICK}
                      axisLine={AXIS}
                      tickLine={AXIS}
                      tickFormatter={yieldTick}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={tipStyle()}
                      formatter={(v, _n, ctx) => [
                        `${Number(v).toFixed(3)}%`,
                        ctx?.payload?.extrapolated
                          ? `${ctx.payload.series} (Extrap)`
                          : ctx?.payload?.series || "Yield",
                      ]}
                      labelFormatter={(t) =>
                        Number(t) < 1
                          ? `${Math.round(Number(t) * 12)} Mo`
                          : `${t}Y`
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="yield_pct"
                      stroke={CURVE}
                      strokeWidth={1.75}
                      dot={false}
                      isAnimationActive
                      animationDuration={350}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="valuation-empty">No Curve Data</div>
              )}
            </div>
          </div>

          <div className="valuation-panel">
            <div className="valuation-panel-head">
              <h2 className="valuation-panel-title">Price Vs Z-Spread</h2>
              <span className="valuation-panel-sub">±25 / ±50 bp</span>
            </div>
            <div className="valuation-chart-wrap">
              {scenarioMatrix.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={scenarioMatrix}
                    margin={{ top: 6, right: 10, left: 0, bottom: 2 }}
                  >
                    <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
                    <XAxis
                      dataKey="label"
                      tick={TICK}
                      axisLine={AXIS}
                      tickLine={AXIS}
                    />
                    <YAxis
                      width={40}
                      tick={TICK}
                      axisLine={AXIS}
                      tickLine={AXIS}
                      tickFormatter={priceTick}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={tipStyle()}
                      formatter={(v, _n, ctx) => [
                        Number(v).toFixed(4),
                        `Δ ${fmtDelta(ctx?.payload?.delta)}`,
                      ]}
                      labelFormatter={(l) => String(l)}
                    />
                    <Bar
                      dataKey="price"
                      isAnimationActive
                      animationDuration={300}
                    >
                      {scenarioMatrix.map((row) => (
                        <Cell
                          key={row.label}
                          fill={row.isBase ? AMBER : BAR}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="valuation-empty">No Price Scenarios</div>
              )}
            </div>
          </div>
        </div>

        <div className="valuation-panel valuation-matrix-panel">
          <div className="valuation-panel-head">
            <h2 className="valuation-panel-title">Risk Matrix</h2>
            <span className="valuation-panel-sub">
              Scenarios · Key Rate Buckets
            </span>
          </div>
          <div className="valuation-matrix-grid">
            <div className="valuation-matrix">
              <div className="valuation-matrix-caption">
                Z-Spread Scenarios
                {payload?.cs01 != null
                  ? ` · CS01 ${fmtDollar(payload.cs01)}/bp`
                  : ""}
              </div>
              <div className="valuation-matrix-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th className="num">Z</th>
                      <th className="num">Price</th>
                      <th className="num">Δ Price</th>
                      <th className="num">Δ NPV</th>
                      <th className="num">CS01 $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenarioMatrix.map((row) => (
                      <tr
                        key={row.label}
                        className={row.isBase ? "is-base" : undefined}
                      >
                        <td>{row.label}</td>
                        <td className="num">{fmtNum(row.z, 0)}</td>
                        <td className="num">{fmtNum(row.price, 4)}</td>
                        <td
                          className={`num${
                            row.delta > 0
                              ? " is-up"
                              : row.delta < 0
                                ? " is-down"
                                : ""
                          }`}
                        >
                          {row.isBase ? "—" : fmtDelta(row.delta)}
                        </td>
                        <td
                          className={`num${
                            row.deltaNpv > 0
                              ? " is-up"
                              : row.deltaNpv < 0
                                ? " is-down"
                                : ""
                          }`}
                        >
                          {row.isBase ? "—" : fmtDollar(row.deltaNpv)}
                        </td>
                        <td
                          className={`num${
                            row.cs01Pnl > 0
                              ? " is-up"
                              : row.cs01Pnl < 0
                                ? " is-down"
                                : ""
                          }`}
                        >
                          {row.isBase ? "—" : fmtDollar(row.cs01Pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="valuation-matrix">
              <div className="valuation-matrix-caption">Key Rate Durations</div>
              <div className="valuation-matrix-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Tenor</th>
                      <th className="num">Duration</th>
                      <th className="num">DV01</th>
                      <th className="num">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {krdMatrix.items.map((row) => (
                      <tr key={row.label}>
                        <td>{row.label}</td>
                        <td className="num">{fmtNum(row.duration, 3)}</td>
                        <td className="num">{fmtDollar(row.dv01)}</td>
                        <td className="num valuation-share-cell">
                          <PctBar pct={row.pct} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {krdMatrix.items.length > 0 && (
                    <tfoot>
                      <tr>
                        <td>Total</td>
                        <td className="num">{fmtNum(krdMatrix.totalDur, 3)}</td>
                        <td className="num">
                          {fmtDollar(krdMatrix.totalDv01)}
                        </td>
                        <td className="num">100%</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
