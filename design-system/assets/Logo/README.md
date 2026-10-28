Six files, all fixed artwork — a logo's color is brand identity, not a theme, so none of these use `currentColor` or CSS tokens the way the icon set does.

- **`strydr-mark.svg`** — the symbol alone: one coral (`#ff5a36`) stride-curve stroke, drawn from the same arc language as the cover's track-curve pattern. Transparent background, works on either theme as-is since coral reads clearly on both.
- **`strydr-app-icon.svg`** — the mark in white on a solid coral rounded-square tile (1024×1024, so it's a direct drop-in for a home-screen or PWA icon).
- **`strydr-wordmark.svg`** — "Strydr" set in Space Grotesk Bold, outlined to paths (not live text, so it renders identically with no font dependency), filled in `ink` (`#16181d`) for light surfaces.
- **`strydr-wordmark-dark.svg`** — the same outlines, filled in light `ink` (`#f4f5f7`) for dark surfaces.
- **`strydr-lockup.svg`** / **`strydr-lockup-dark.svg`** — mark and wordmark together, coral mark at left, ink wordmark at right, in the same two surface variants.

Use the `-dark` variant on a dark or photographic background rather than placing the light-surface file there — don't rely on the glass material or a CSS filter to make the light version read on dark. Never recolor, restyle, stretch, or redraw any of the six; if a context needs a color this set doesn't cover, that's a new file to ask for, not a tint applied in code.
