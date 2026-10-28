The app's four fixed destinations, in one floating glass bar: Dashboard, Routes, Coach, Profile. All four are flat — Strydr reads data recorded on the watch, so there's no record or start action anywhere in the app, and the bar has no elevated button.

The bar is `glass glass--sm` — the lighter blur, because it sits over content that scrolls underneath it constantly and a heavier blur would lag visibly on scroll. It floats `space-4` above the bottom edge and never touches the screen's edges.

An active tab's icon and label both switch to `accent-text`; an inactive tab stays `ink-secondary`. Never show the active state by icon fill alone — the label's color changes too, so the active tab still reads correctly to a color-blind runner glancing down mid-stride. Labels are always present under every icon; Strydr has no icon-only tab bar.

Icons are the real set now — see the Icons card for the full thirteen and their source markup.
