# CashFlow theme

Dense Bloomberg Terminal–style UI matched to `docs/bloomberg-terminal-pure-factor-returns.png` (733×355). Black field, near-white type, golden amber accents. Small fonts. 32px header with **v0.1.0**.

## Top bar

Height **32px**. Pure black. Near-white uppercase **CashFlow** + amber **v0.1.0**. Hairline bottom border `#323232`.

## Palette

Pixel-sampled from the Terminal screenshot. Amber accent family kept at `#FD9D24` (bright glyph peaks `#F29C29`–`#FDA432`; anti-aliased median darker).

| Token | Hex | Role | Notes vs prior |
| --- | --- | --- | --- |
| Background | `#000000` | Page / shell | unchanged |
| Background deep | `#000000` | Top bar | was `#010101` → pure black |
| Panel | `#212026` | Section panels | unchanged (matches `#1F201C`–`#212123` cluster) |
| Grid mute | `#0C0C0C` | Table header / deep chrome | was `#1A1A1A` |
| Row alt | `#121212` | Odd rows | new / was odd `#1A1A1A` |
| Text | `#FCFCFC` | Primary type | unchanged (`#FFFFFF` also common) |
| Text muted | `#808080` | Column headers / axis ticks | unchanged (also `#727272`) |
| Accent | `#FD9D24` | Labels / CTA / chart / version | unchanged |
| Accent bright | `#FCA024` | Hover / highlight | unchanged |
| Hairline | `#323232` | Borders / grid lines | was `#585858` (sampled `#323232`/`#2D2D2D`) |
| Chrome | `#464646` | Input borders | new (sampled mid-gray) |
| Up | `#43BC67` | Positive | was `#40B065` (sampled cell green) |
| Down | `#C51D46` | Negative | was `#C41E3A` (sampled `#CD2047`/`#C51D46`) |

## Typography

**Source Sans 3** (Google Fonts, OFL) — dense UI sans for body, header, AG Grid, Recharts.

Terminal historically used proprietary Matthew Carter faces (**Bloomberg Prop Unicode** / **Bloomberg Fixed Unicode**); bloomberg.com serves **Bloomberg** / **Bloomberg-PropU_N** / **Bloomberg-Sans** via Bloomberg’s font service — not licensed for third-party apps. Source Sans 3 is the closest widely available match (base of Bergoom, an open Terminal recreation). Fallback: `"Segoe UI", system-ui, sans-serif`. Tabular figures via `font-feature-settings: "tnum" 1`.

Sizes: body 12px / lh 1.25; labels 10px caps amber; table cells 11px; header rows 22px; top bar name 12px; version 10px.

## Density / chrome

- Section padding `6–8px`, main gap `6px` (tighter than prior `10–12px`).
- AG Grid: `rowHeight`/`headerHeight` **22**, spacing **2**, square corners, hairline `#323232` row/column borders.
- Recharts: solid `#323232` horizontal grid, 10px ticks, square bars (no radius).
- Field labels amber uppercase (Terminal filter-label pattern).
- Buttons square, black text on amber.

## Favicon

`public/favicon.svg` — black field, amber stylized **C** + rising bars; wired in `index.html`.
