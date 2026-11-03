# CashFlow theme

Dense Bloomberg Terminal–style UI with a **deep navy** field (sample `docs/theme-navy-sample.png`, ~`#001A41`), near-white type, golden amber accents. Small fonts. 32px header with **v0.1.0**. Source Sans 3 unchanged.

## Top bar

Height **32px**. Deep navy (`--cf-bg-deep`). Near-white uppercase **CashFlow** + amber **v0.1.0**. Hairline bottom border `#2A3D5C`.

## Palette

Navy family replaces pure black / near-black chrome. Amber accent kept at `#FD9D24`. Up/down greens and reds unchanged.

| Token | Hex | Role | Notes vs prior |
| --- | --- | --- | --- |
| Background | `#001A41` | Page / shell | was `#000000` → deep midnight navy |
| Background deep | `#001636` | Top bar / sidenav | was `#000000` / `#010101` |
| Panel | `#0A274F` | Section panels | was `#212026` |
| Grid mute | `#001538` | Table header / deep chrome | was `#0C0C0C` |
| Row alt | `#0A2348` | Odd rows | was `#121212` |
| Row hover | `#0D274C` | Grid hover | was `#1A1A1A` |
| Text | `#FCFCFC` | Primary type | unchanged (`#FFFFFF` also fine) |
| Text muted | `#808080` | Column headers / axis ticks | unchanged |
| Accent | `#FD9D24` | Labels / CTA / chart / version | unchanged |
| Accent bright | `#FCA024` | Hover / highlight | unchanged |
| Hairline | `#2A3D5C` | Borders / grid lines | was `#323232` (navy-tinted) |
| Chrome | `#4A5F7A` | Input borders | was `#464646` (navy-tinted) |
| Up | `#43BC67` | Positive | unchanged |
| Down | `#C51D46` | Negative | unchanged |
| On-accent | `#001A41` | Button / active-nav type on amber | was `#000000` |

## Typography

**Source Sans 3** (Google Fonts, OFL) — dense UI sans for body, header, AG Grid, Recharts.

Terminal historically used proprietary Matthew Carter faces (**Bloomberg Prop Unicode** / **Bloomberg Fixed Unicode**); bloomberg.com serves **Bloomberg** / **Bloomberg-PropU_N** / **Bloomberg-Sans** via Bloomberg’s font service — not licensed for third-party apps. Source Sans 3 is the closest widely available match (base of Bergoom, an open Terminal recreation). Fallback: `"Segoe UI", system-ui, sans-serif`. Tabular figures via `font-feature-settings: "tnum" 1`.

Sizes: body 12px / lh 1.25; labels 10px caps amber; table cells 11px; header rows 22px; top bar name 12px; version 10px.

## Density / chrome

- Section padding `6–8px`, main gap `6px` (tighter than prior `10–12px`).
- AG Grid: `rowHeight`/`headerHeight` **22**, spacing **2**, square corners, hairline `#2A3D5C` row/column borders.
- Recharts: solid `#2A3D5C` horizontal grid, 10px ticks, square bars (no radius).
- Field labels amber uppercase (Terminal filter-label pattern).
- Buttons square, navy text on amber.

## Favicon

`public/favicon.svg` — navy field `#001A41`, amber stylized **C** + rising bars; wired in `index.html`.
