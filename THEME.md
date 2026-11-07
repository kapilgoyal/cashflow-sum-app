# CashFlow theme

**Bloomberg Terminal–inspired dark** UI: near-black panes, amber (`#FD9D24`) accents, monospace-leaning terminal fonts. Dense high-contrast grids. Title Case labels (no CSS uppercase). Header with brand + version on the **left**. Collapsible left nav: **icons only** when collapsed, **icon + label** when expanded.

## Top bar / nav

Height **36px** default, **44px** from 1280px, **52px** from 1600px (**44px** on phone). Pure black `#000000`. Left: hamburger/close · white **CashFlow** · amber **v0.3.0**. Desktop sidenav is a near-black strip with amber selected tab (black type on amber). Collapsible (persisted). On phone (≤720px): collapsed = no rail (full-bleed content); hamburger opens a left drawer over a dimmed backdrop; tap targets ≥44px.

## Palette

| Token | Hex | Role |
| --- | --- | --- |
| Background | `#000000` | Main content / page |
| Background deep | `#000000` | Top bar / KPI chips |
| Nav strip | `#0A0A0A` | Collapsible sidenav |
| Panel | `#212026` | Section containers |
| Text | `#FCFCFC` | Primary type |
| Text muted | `#808080` | Headers / meta |
| Accent | `#FD9D24` | CTA / selected nav / version |
| Accent bright | `#FCA024` | Hover |
| Hairline | `#323232` | Borders / grid lines |
| Chrome | `#464646` | Input borders / scroll thumbs |
| Grid mute | `#0C0C0C` | Table header |
| Row alt | `#121212` | Odd rows |
| Row hover | `#1A1A1A` | Grid hover |
| Selected | `#2A2418` | Selected grid row |
| On-accent | `#000000` | Type on amber |
| Nav text | `#C8C8C8` | Inactive sidenav labels |
| Up | `#43BC67` | Positive |
| Down | `#C51D46` | Negative |

## Typography

**IBM Plex Mono** + **Roboto Mono** (Google Fonts, OFL). Fallback: `ui-monospace, Menlo, monospace`. Tabular figures via `font-feature-settings: "tnum" 1`. Title Case for nav, menus, headers, KPIs, and static text (not CSS uppercase).

| Viewport | Body | Labels | Grid cells | KPI value | Controls |
| --- | --- | --- | --- | --- | --- |
| Default | 12px | 10px | 11px | 14px | 28px |
| ≥1280px | 14px | 12px | 13px | 18px | 34px |
| ≥1600px | 16px | 13px | 15px | 22px | 40px |
| Phone | compact type | — | — | — | ≥44px taps |

## Density / chrome

- Section padding `8–10px`, main gap `6–8px` (more padding on ≥1600px).
- AG Grid dark Quartz params; compact `rowHeight`/`headerHeight` **20/22** by default, **28/32** at 1280px, **34/38** at 1600px. Square corners.
- No heavy outer grid/section frame (`wrapperBorder: false`); light row/column hairlines only.
- KPI strip: black chips, light type, amber underline when active.
- Responsive: strat charts stack; touch-sized export/copy icons; mobile hamburger drawer.
- Field labels muted Title Case.
- Buttons square, black text on amber.
- No purple glow effects.
