# CashFlow theme

Professional **light** UI: white main content, navy (`#001A41`) typography, navy top bar, light-blue collapsible sidenav strip, amber accents. Source Sans 3 unchanged. Small fonts. Header with brand + version on the **left**.

## Top bar / nav

Height **36px** (48px on phone). Deep navy `#001A41`. Left: hamburger/close · white uppercase **CashFlow** · amber **v0.3.0**. Desktop sidenav is a light-blue strip (`#E8F0FE`) with navy labels; selected tab amber + navy text. Collapsible (persisted). On phone (≤720px): collapsed = no rail (full-bleed content); hamburger opens a left drawer over a dimmed backdrop; tap targets ≥44px.

## Palette

| Token | Hex | Role |
| --- | --- | --- |
| Background | `#FFFFFF` | Main content / page |
| Background deep | `#001A41` | Top bar |
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

**Source Sans 3** (Google Fonts, OFL). Fallback: `"Segoe UI", system-ui, sans-serif`. Tabular figures via `font-feature-settings: "tnum" 1`.

Sizes: body 12px / lh 1.25; labels 10px caps; table cells 11px; top bar name 13px; version 10px.

## Density / chrome

- Section padding `8–10px`, main gap `8px`.
- AG Grid light Quartz params; denser `rowHeight`/`headerHeight` **20/22**, spacing **2** (font size unchanged), square corners.
- Responsive: strat charts stack; touch-sized export/copy icons; mobile nav drawer.
- Field labels muted navy uppercase.
- Buttons square, navy text on amber.

## Favicon

`public/favicon.svg` — navy field `#001A41`, amber stylized **C** + rising bars; wired in `index.html`.
