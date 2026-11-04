# Demo data and docs screenshots

Every screenshot in `docs/images/` comes from a **made-up runner** in Central Park, never from real data. This folder
rebuilds that runner and retakes the screenshots.

| File | What it does |
|---|---|
| `generate.py` | Writes fully synthetic Health Auto Export JSON: 20 weeks (2026-06-15 to 2026-11-03) of runs on three routes, a few walks with a carried weight, watch strength workouts, resting HR, HRV, sleep, steps and weight |
| `seed.py` | Through the API of a running demo server: profile (HRmax 190, no birth year or sex), shoes, three home-workout plans, 18 sessions, a run note, a week note, and weather lookup on |
| `shoot.mjs` | Takes screenshots with headless Chrome (puppeteer-core) |
| `make-screenshots.sh` | Does all of it in a temp folder and writes WebP files to `docs/images/` |

```sh
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" fixtures/demo/make-screenshots.sh
```

It needs uv, Node.js, curl, ImageMagick and `cwebp`. The server runs on `127.0.0.1:8090/8091` only, with a throwaway
key and database that are deleted afterwards. Weather lookup sends grid cells around Central Park to Open-Meteo.

Workout IDs are deterministic (`generate.wid(label)`), so the run, route and week used in the shots stay the same.
Dates are fixed, so the "this week" cards look as they did on 2026-11-04 only when the shots are taken that week; later
shots show an older week as current. Shift `START` and `END` in `generate.py` to move the block.
