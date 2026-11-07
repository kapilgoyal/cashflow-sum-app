# CashFlow theme

Professional **light** UI: white main content, navy (`#001A41`) typography, navy top bar, light-blue collapsible sidenav strip, amber accents. Source Sans 3 unchanged. Header with brand + version on the **left**. Title Case labels (no extra chrome). KPI chips use the same navy as charts.

## Top bar / nav

Height **36px** default, **44px** from 1280px, **52px** from 1600px (**44px** on phone). Deep navy `#001A41`. Left: hamburger/close · white **CashFlow** · amber **v0.3.0**. Desktop sidenav is a light-blue strip (`#E8F0FE`) with navy Title Case labels; selected tab amber + navy text. Collapsible (persisted). On phone (≤720px): collapsed = no rail (full-bleed content); hamburger opens a left drawer over a dimmed backdrop; tap targets ≥44px.

## Palette

| Token | Hex | Role |
| --- | --- | --- |
| Background | `#FFFFFF` | Main content / page |
| Background deep | `#001A41` | Top bar / KPI chips |
| Nav strip | `#E8F0FE` | Collapsible sidenav |
| Panel | `#FFFFFF` | Section containers |
| Text | `#001A41` | Primary type on white |
| Text muted | `#4A5F7A` | Headers / meta |
| Accent | `#FD9D24` | CTA / selected nav / version |
| Accent bright | `#FCA024` | Hover |
| Hairline | `#D0D7E2` | Borders / grid lines |
| Chrome | `#8A9BB0` | Input borders / scroll thumbs |
| Grid mute | `#F4F6F9` | Table header |
| Row alt | `#F7F9FC` | Odd rows |
| Row hover | `#EEF2F7` | Grid hover |
| Selected | `#E8F0FE` | Selected grid row |
| On-accent | `#001A41` | Type on amber |
| Nav text | `#001A41` | Inactive sidenav labels |
| Up | `#1F8A44` | Positive |
| Down | `#C51D46` | Negative |

## Typography

**Source Sans 3** (Google Fonts, OFL). Fallback: `"Segoe UI", system-ui, sans-serif`. Tabular figures via `font-feature-settings: "tnum" 1`. Title Case for nav, menus, headers, KPIs, and static text (not CSS uppercase).

| Viewport | Body | Labels | Grid cells | KPI value | Controls |
| --- | --- | --- | --- | --- | --- |
| Default | 12px | 10px | 11px | 14px | 28px |
| ≥1280px | 14px | 12px | 13px | 18px | 34px |
| ≥1600px | 16px | 13px | 15px | 22px | 40px |
| Phone | compact type | — | — | — | ≥44px taps |

## Density / chrome

- Section padding `8–10px`, main gap `8px` (more padding on ≥1600px).
- AG Grid light Quartz params; compact `rowHeight`/`headerHeight` **20/22** by default, **28/32** at 1280px, **34/38** at 1600px. Square corners.
- No heavy outer grid/section frame (`wrapperBorder: false`); light row/column hairlines only.
- KPI strip: navy `#001A41` chips, white type, amber underline when active.
- Responsive: collateral charts stack; touch-sized export/copy icons; mobile hamburger drawer.
- Money whole dollars; counts/FICO integers; LTV/DTI ~1 decimal; WAC 2 decimals.
- Field labels muted navy Title Case.
- Buttons square, navy text on amber.
