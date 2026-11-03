# CashFlow theme

Professional **light** UI: white main content, navy (`#001A41`) typography, navy chrome for top bar / sidenav, amber accents. Source Sans 3 unchanged. Small fonts. Header with **v0.1.0**.

## Top bar / nav

Height **36px**. Deep navy `#001A41`. White uppercase **CashFlow** + amber **v0.1.0**. Sidenav on navy with light readable labels (`#D7E0EC`); selected tab amber background with navy text.

## Palette

| Token | Hex | Role |
| --- | --- | --- |
| Background | `#FFFFFF` | Main content / page |
| Background deep | `#001A41` | Top bar / sidenav |
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
| Nav text | `#D7E0EC` | Inactive sidenav labels |
| Up | `#1F8A44` | Positive |
| Down | `#C51D46` | Negative |

## Typography

**Source Sans 3** (Google Fonts, OFL). Fallback: `"Segoe UI", system-ui, sans-serif`. Tabular figures via `font-feature-settings: "tnum" 1`.

Sizes: body 12px / lh 1.25; labels 10px caps; table cells 11px; top bar name 13px; version 10px.

## Density / chrome

- Section padding `8–10px`, main gap `8px`.
- AG Grid light Quartz params; `rowHeight`/`headerHeight` **24/28**, spacing **4**, square corners.
- Field labels muted navy uppercase.
- Buttons square, navy text on amber.

## Favicon

`public/favicon.svg` — navy field `#001A41`, amber stylized **C** + rising bars; wired in `index.html`.
