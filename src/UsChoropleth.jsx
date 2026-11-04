/**
 * Lightweight choropleths for Stratification — no map library deps.
 * State: simplified SVG paths. ZIP3: concentration tile grid.
 */
import { US_MAP_VIEWBOX, US_STATE_PATHS } from "./usStatePaths";

function scaleColor(t, { low = "#E8EEF5", high = "#001A41" } = {}) {
  const x = Math.max(0, Math.min(1, t));
  const parse = (hex) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
  const [r1, g1, b1] = parse(low);
  const [r2, g2, b2] = parse(high);
  const r = Math.round(r1 + (r2 - r1) * x);
  const g = Math.round(g1 + (g2 - g1) * x);
  const b = Math.round(b1 + (b2 - b1) * x);
  return `rgb(${r},${g},${b})`;
}

function maxValue(rows, valueKey) {
  let m = 0;
  for (const row of rows || []) {
    const v = Number(row[valueKey]) || 0;
    if (v > m) m = v;
  }
  return m || 1;
}

export function StateChoropleth({
  rows,
  metric = "upb",
  selected,
  onSelect,
  fmtTip,
}) {
  const valueKey = metric === "loans" ? "loan_count" : "upb";
  const byState = new Map();
  for (const row of rows || []) {
    const st = String(row.bucket || "")
      .trim()
      .toUpperCase();
    if (st && st !== "MISSING") byState.set(st, row);
  }
  const max = maxValue([...byState.values()], valueKey);

  return (
    <div className="choropleth choropleth-state">
      <svg
        viewBox={US_MAP_VIEWBOX}
        role="img"
        aria-label="US State Concentration Map"
        className="choropleth-svg"
      >
        {Object.entries(US_STATE_PATHS).map(([abbr, d]) => {
          const row = byState.get(abbr);
          const v = row ? Number(row[valueKey]) || 0 : 0;
          const fill = row ? scaleColor(v / max) : "#F3F5F8";
          const isSel = selected === abbr;
          const tip = row
            ? `${abbr}: ${fmtTip ? fmtTip(v) : v}`
            : `${abbr}: None`;
          return (
            <path
              key={abbr}
              d={d}
              fill={fill}
              stroke={isSel ? "#FD9D24" : "#FFFFFF"}
              strokeWidth={isSel ? 2.2 : 0.6}
              className={`choropleth-state-path${row ? " is-clickable" : ""}${
                isSel ? " is-selected" : ""
              }`}
              tabIndex={row ? 0 : undefined}
              role={row ? "button" : undefined}
              aria-label={tip}
              onClick={() => row && onSelect?.(abbr, row)}
              onKeyDown={(e) => {
                if (!row) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect?.(abbr, row);
                }
              }}
            >
              <title>{tip}</title>
            </path>
          );
        })}
      </svg>
      <div className="choropleth-legend" aria-hidden="true">
        <span>Low</span>
        <span
          className="choropleth-swatch"
          style={{
            background: `linear-gradient(90deg, #E8EEF5, #001A41)`,
          }}
        />
        <span>High</span>
      </div>
    </div>
  );
}

/** ZIP3 concentration tiles — choropleth grid when postal_code exists. */
export function Zip3Choropleth({
  rows,
  metric = "upb",
  selected,
  onSelect,
  fmtTip,
  limit = 96,
}) {
  const valueKey = metric === "loans" ? "loan_count" : "upb";
  const sorted = [...(rows || [])]
    .filter((r) => r.bucket && r.bucket !== "missing")
    .sort((a, b) => (Number(b[valueKey]) || 0) - (Number(a[valueKey]) || 0))
    .slice(0, limit);
  const max = maxValue(sorted, valueKey);

  if (!sorted.length) {
    return <p className="muted strat-chart-empty">No ZIP3 Buckets</p>;
  }

  return (
    <div className="choropleth choropleth-zip3">
      <div className="zip3-grid" role="list" aria-label="ZIP3 Concentration">
        {sorted.map((row) => {
          const v = Number(row[valueKey]) || 0;
          const isSel = selected === row.bucket;
          const tip = `${row.bucket}: ${fmtTip ? fmtTip(v) : v}`;
          return (
            <button
              key={row.bucket}
              type="button"
              role="listitem"
              className={`zip3-cell${isSel ? " is-selected" : ""}`}
              style={{ background: scaleColor(v / max) }}
              title={tip}
              aria-label={tip}
              onClick={() => onSelect?.(row.bucket, row)}
            >
              <span className="zip3-code">{row.bucket}</span>
            </button>
          );
        })}
      </div>
      <div className="choropleth-legend" aria-hidden="true">
        <span>Low</span>
        <span
          className="choropleth-swatch"
          style={{
            background: `linear-gradient(90deg, #E8EEF5, #001A41)`,
          }}
        />
        <span>High</span>
      </div>
    </div>
  );
}
