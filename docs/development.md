# Development

How to run Strydr from source, run the tests, and find your way around the code.

## Prerequisites

- **Python 3.14** and [uv](https://docs.astral.sh/uv/). `uv sync` installs everything, including the `sqlcipher3`
  wheel.
- **Node.js** 22.18+ or 24.12+, for the web app.
- `yt-dlp`, for YouTube import, comes with the Python dependencies.

## Run it

Keep your development data **outside the repository**:

```sh
# Backend
cd backend
uv sync
mkdir -p ~/strydr-dev-data
openssl rand -hex 32 > ~/strydr-dev-data/db.key && chmod 600 ~/strydr-dev-data/db.key
export STRYDR_DB_KEY_FILE=~/strydr-dev-data/db.key
export STRYDR_DB_PATH=~/strydr-dev-data/strydr.db
export STRYDR_HOME_TZ=Europe/London          # optional

uv run strydr init                            # prompts for a password, prints the ingest token
uv run strydr serve                           # app :8080, ingest :8081, one job worker
```

```sh
# Frontend, in a second terminal, with hot reload
cd web
npm install
npm run dev                                   # Vite on :5173, proxies /api to :8080
```

Open `http://localhost:5173`. To serve the built app from the backend instead, run `npm run build` and start the server
with `STRYDR_WEB_DIST=/path/to/strydr/web/dist`.

### Load some data

Send the synthetic fixtures to your dev server:

```sh
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  --data-binary @fixtures/hae-export.json http://localhost:8081/ingest/hae
```

Or upload a generated Apple export from `fixtures/apple_health_export` (zip it first) in Settings.

## Tests

```sh
cd backend && uv run pytest -q          # backend
cd web && npm test                      # web unit tests (Vitest)
cd web && npm run build                 # also runs vue-tsc type checks
```

Tests use **synthetic fixtures only**. Never add real health data, real GPS tracks, real names or device identifiers
to the repository, including in screenshots and test snapshots.

## Fixtures

- `fixtures/generate_hae_export.py` writes fully synthetic Health Auto Export JSON (a fake watch, an arbitrary city,
  fixed fake dates, seeded noise): per-minute and per-second heart rate, a resend, a richer copy, strength workouts.
- `fixtures/generate_apple_export.py` writes a synthetic Apple Health export.

Regenerate with `python fixtures/generate_hae_export.py` (or the Apple one) after changing them.

## API contract

The app-port API schema is committed as `backend/openapi.json`. After changing an endpoint:

```sh
cd backend && uv run strydr openapi          # writes openapi.json
cd web && npm run gen:api:file               # regenerates src/api/schema.d.ts
```

## Database migrations

Migrations are Alembic scripts in `backend/strydr/store/migrations/versions/` and run automatically on `strydr serve`.
A migration that adds a column to an analytic table does not recompute by itself; enqueue a recompute after deploying
it.

## Where things live

| To change | Look in |
|---|---|
| How a source is parsed | `backend/strydr/sources/hae/adapter.py`, `sources/apple/adapter.py` (bump `ADAPTER_VERSION`) |
| A derived metric | `backend/strydr/pipeline/derive/` |
| An insight rule | `backend/strydr/pipeline/insights/rules/` and its template in `insights/templates/definitions.py` |
| A threshold default | `backend/config/thresholds.toml` |
| Route matching | `backend/strydr/pipeline/derive/routes/`, `backend/config/routes.toml` |
| An API endpoint | `backend/strydr/api/` |
| What may leave the server | `backend/strydr/egress/payload.py` |
| A page | `web/src/views/` |
| Shared UI | `web/src/components/ui/` (design system) and `components/app/` |
| Live workout timing | `web/src/lib/workoutEngine.ts` |
| Colours, type, spacing | `web/src/styles/tokens.css` (generated from `design-system/tokens.json` by `npm run gen:tokens`) |

See [Architecture](architecture.md) for how the pieces connect.

## Conventions

- **Pure pipeline.** Code in `pipeline/derive` and `pipeline/insights` takes plain values and returns plain values: no
  database, clock or network.
- **Tunable numbers live in TOML,** not in code.
- **Errors and logs carry no data:** exception class names only, never values, names, dates or locations.
- **Plain wording.** Insight text describes patterns; it never diagnoses or prescribes. New templates must pass the
  banned-terms check.
- **UI:** never fix crowding by shrinking type; regroup or move things. Keep controls off maps. Every chart has a
  **View as table**.

## Contributing

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Branch from `main`, keep the change focused, and add tests on synthetic data.
3. Run the full backend and web suites and the web build before opening a pull request.
4. Describe what changed and how you checked it.
