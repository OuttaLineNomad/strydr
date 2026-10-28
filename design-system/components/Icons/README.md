Strydr's first real icon set — thirteen glyphs, replacing the placeholder outlines used in earlier drafts of Tab Bar and Button. Custom-drawn rather than pulled from a named library, so every icon shares the exact stroke weight and corner language as the rest of the system (and nothing here depends on an external icon package).

One rule for all thirteen: **24×24 viewBox, 1.8px stroke, round caps and joins, no fill** — the two single exceptions are `speed`'s pivot dot (a tiny filled circle, the needle needs a visible hinge) and `dashboard`, whose three bars use a heavier 2.4px stroke with round caps so they read as solid bars rather than thin outlines at nav size. Icons take their color from `currentColor` — set `color: var(--ink)`, `var(--ink-secondary)`, or `var(--accent-text)` on a parent, never hardcode a fill. Default size is 24px; nav-bar and button icons commonly run at 20–22px, never below 18px or the strokes start to merge.

| Icon | Usage |
|---|---|
| `dashboard` | Tab bar — the Dashboard destination |
| `routes` | Tab bar — the Routes destination; also any map/GPS context |
| `coach` | Tab bar — the Coach destination (a conversation, not a sparkle — deliberately avoids the AI-sparkle cliché) |
| `profile` | Tab bar — the Profile destination |
| `sync` | The primary "pull latest data" action — buttons, pull-to-refresh |
| `share` | Export or share a route, a run, a chart |
| `pr / trophy` | Personal records and achievement badges — pairs with `tertiary` |
| `pace` | The `chart-pace` series; pace stat tiles |
| `heart rate` | The `chart-heart-rate` series; HR stat tiles |
| `elevation` | The `chart-elevation` series; elevation stat tiles |
| `cadence` | The `chart-cadence` series — an abstract step-rhythm mark, not literal footprints |
| `power` | The `chart-power` series |
| `speed` | The `chart-speed` series |

Copy any glyph's inner markup into your own `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">…</svg>` wrapper:

```html
<!-- dashboard (stroke-width 2.4) -->
<line x1="6" y1="18" x2="6" y2="13"/><line x1="12" y1="18" x2="12" y2="7"/><line x1="18" y1="18" x2="18" y2="4"/>

<!-- routes -->
<path d="M9 3 4 5v16l5-2 6 2 5-2V3l-5 2-6-2Z"/><path d="M9 3v16M15 5v16"/>

<!-- coach -->
<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H9l-4 4v-4H6.5A2.5 2.5 0 0 1 4 13.5v-8Z"/>

<!-- profile -->
<circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.9 3.1-6 7-6s7 2.1 7 6"/>

<!-- sync -->
<path d="M20 11a8 8 0 0 0-14.9-3.5M4 13a8 8 0 0 0 14.9 3.5"/><path d="M20 4v4h-4M4 20v-4h4"/>

<!-- share -->
<path d="M12 15V4M8 8l4-4 4 4"/><path d="M5 13v5.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V13"/>

<!-- pr / trophy -->
<path d="M8 4h8v3a4 4 0 0 1-8 0V4Z"/><path d="M8 5H5.5A1.2 1.2 0 0 0 4.3 6.2 3 3 0 0 0 7 9M16 5h2.5a1.2 1.2 0 0 1 1.2 1.2A3 3 0 0 1 17 9"/><path d="M12 11v3"/><path d="M9 20h6"/><path d="M10.2 20v-1.5a1.8 1.8 0 0 1 3.6 0V20"/>

<!-- pace -->
<circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l3 2"/><path d="M9.5 2.5h5M12 2.5V5"/>

<!-- heart rate -->
<path d="M12 19.5s-7.5-4.6-9.3-9.4C1.6 6.9 3.4 4 6.5 4c2 0 3.4 1.2 4 2.3.6-1.1 2-2.3 4-2.3 3.1 0 4.9 2.9 3.8 6.1C19.5 14.9 12 19.5 12 19.5Z"/>

<!-- elevation -->
<path d="M3 18 9 8l4 6 2-3 6 7H3Z"/>

<!-- cadence -->
<ellipse cx="9" cy="7" rx="2.3" ry="3.2" transform="rotate(-15 9 7)"/><ellipse cx="15" cy="17" rx="2.3" ry="3.2" transform="rotate(15 15 17)"/>

<!-- power -->
<path d="M13 3 5 14h5l-1 7 8-11h-5l1-7Z"/>

<!-- speed (pivot dot is filled, not stroked) -->
<path d="M4 16a8 8 0 0 1 16 0"/><path d="M12 16 16 9"/><circle cx="12" cy="16" r="1.3" fill="currentColor" stroke="none"/>
```

These are inline markup, not asset files on purpose — an uploaded SVG asset renders through `<img>` and can't pick up `currentColor` or theme with the page, so it could never show the active-tab coral or dim correctly for a disabled state. The logo is the opposite case (fixed brand artwork, never recolored) and lives under `assets/Logo/` instead.

Growing the set: next likely additions are `calendar`/date-range, `chevron`, `close`, `check`, `search` and a `warning`/alert glyph for sync errors — add them at 24×24 with the same 1.8px stroke rather than reaching for a library partway through.
