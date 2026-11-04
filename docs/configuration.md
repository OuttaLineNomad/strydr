# Configuration

Most settings live in the app (**Settings**) and are stored in the encrypted database. This page covers what is set
outside it: environment variables, the command line, and the tuning files.

- [Environment variables](#environment-variables)
- [CLI](#cli)
- [Thresholds](#thresholds)
- [Route matching](#route-matching)
- [API](#api)

## Environment variables

Secrets come from files, never from environment values.

| Variable | Default | Meaning |
|---|---|---|
| `STRYDR_DB_PATH` | `/data/strydr.db` | The encrypted database |
| `STRYDR_DB_KEY_FILE` | `/run/secrets/strydr_db_key` | File holding the database key (64 hex characters from `openssl rand -hex 32`) |
| `STRYDR_DATA_DIR` | folder of `STRYDR_DB_PATH` | Where `backups/` snapshots go |
| `STRYDR_HOME_TZ` | `TZ`, else `UTC` | Default home time zone (you can change it in Settings) |
| `STRYDR_HOST` | `0.0.0.0` | Address both ports listen on |
| `STRYDR_APP_PORT` | `8080` | Web app and API |
| `STRYDR_INGEST_PORT` | `8081` | Health Auto Export ingest |
| `STRYDR_WEB_DIST` | `/app/web/dist` | The built web app served by the app port |
| `STRYDR_YTDLP` | `yt-dlp` on `PATH` | Path to yt-dlp, for [YouTube import](home-workouts.md#from-a-youtube-short) |
| `STRYDR_RETRY_BACKOFF_S` | `5` | Base delay before a failed job is retried (it doubles each attempt) |

With Docker Compose, set `TZ` in your shell or in `.env`; the database key is the Compose secret
`secrets/strydr_db_key`.

## CLI

The `strydr` command (`uv run strydr ...` in development, `docker compose run --rm strydr ...` in Docker):

| Command | What it does |
|---|---|
| `strydr serve` | Runs the app (`:8080`), the ingest (`:8081`) and one background job worker. Runs migrations on start |
| `strydr init [--username NAME] [--password-file FILE]` | Creates the single user (default `runner`) and prints the ingest token once. The password must be 8 characters or more |
| `strydr init --reset` | Replaces the user and issues a new ingest token. Your data stays |
| `strydr relabel --from walk --to run --through YYYY-MM-DD` | Changes the type of every matching workout up to and including that local date, then recomputes. `--from` can be `run`, `walk`, `hike` or `strength`; `--to` can be `run`, `walk` or `hike`. Later and future imports keep the type the watch sends |
| `strydr openapi [--out FILE]` | Writes the API schema (`openapi.json`). Needs no database |

## Thresholds

The cut-offs behind insights, load and days are in [`backend/config/thresholds.toml`](../backend/config/thresholds.toml),
one section per rule or stage. Each value is a published default marked as an assumption, meant to be tuned.

You do not need to edit the file: **Settings → Advanced: thresholds** shows every default and lets you override any of
them. Overrides are stored in the database, validated (unknown sections or keys are rejected), and trigger a full
recompute. Remove an override to go back to the default.

Some useful ones:

| Section.key | Default | Effect |
|---|---|---|
| `days.hard_hr_fraction` | `0.88` | Share of HRmax that counts toward a hard day |
| `days.hard_minutes` | `20` | Minutes at that heart rate for a hard day |
| `intensity-mix.min_easy_share_pct` | `70.0` | Below this, the 80/20 insight fires |
| `weekly-ramp.ramp_pct` | `30.0` | Week-over-average increase that counts as a ramp |
| `no-rest-day.enabled` | `true` | Turn off while run-streaking |
| `training-state.enabled` | `true` | Turn the training state off |
| `load.tau_fitness_days` / `load.tau_fatigue_days` | `42` / `7` | Time constants of fitness and fatigue |

The same settings are available over the API: `GET` and `PUT /api/v1/settings/thresholds`.

## Route matching

How repeated routes are found, cut into sections and compared is in
[`backend/config/routes.toml`](../backend/config/routes.toml), in SI units:

- `[routes.match]`: which types form routes (runs), the minimum run length (1 km), GPS coverage (80%), how close starts
  and ends must be (150 m) and the distance tolerance (15%, at least 250 m).
- `[routes.sections]`: how a route is cut into sections.
- `[routes.climbs]`: what counts as a climb.
- `[routes.compare]`: how a section is compared with your usual at a similar heart rate.

These are not exposed in Settings. Edit the file and restart Strydr; the next recompute (after a sync or a settings
change) uses the new values. To fix one grouping,
use **Fix the grouping** on the route page instead.

## API

Everything the web app does goes through a JSON API under `/api/v1` on the app port, authenticated by the session
cookie from `POST /api/v1/auth/login`. The schema is committed as
[`backend/openapi.json`](../backend/openapi.json); regenerate it with `uv run strydr openapi` after changing an
endpoint. The web app's types are generated from it (`npm run gen:api:file`).

The ingest port has one endpoint, `POST /ingest/hae`, authenticated by `Authorization: Bearer <ingest token>`.
