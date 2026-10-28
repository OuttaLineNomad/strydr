# Strydr backend

Python 3.14 + uv. Slice 1: ingest, encrypted store, jobs, session login, sync status.
Slice 2 (backend): analytic generations and `recompute`, profile, run summaries, records, privacy-clipped route geometry, dashboard/run/profile/notes API.
Slice 3-5: the full recompute (profile, summary, load, days, records, routes, insights), week/load/insight/route APIs,
privacy zones, optional AI phrasing through the egress gateway, nightly encrypted snapshots, reparse, and SPA serving.
Regenerate the committed API contract after any endpoint change: `uv run strydr openapi` (writes `openapi.json`).

## Dev setup (macOS arm64)

```sh
uv sync                      # installs everything, incl. the sqlcipher3 arm64 wheel

# Dev DB key and data live OUTSIDE the repo.
mkdir -p ~/strydr-dev-data
openssl rand -hex 32 > ~/strydr-dev-data/db.key && chmod 600 ~/strydr-dev-data/db.key
export STRYDR_DB_KEY_FILE=~/strydr-dev-data/db.key
export STRYDR_DB_PATH=~/strydr-dev-data/strydr.db
export STRYDR_HOME_TZ=Europe/London         # optional; defaults to TZ, then UTC

uv run strydr init           # prompts for a password, prints the ingest token once
uv run strydr serve          # app :8080, ingest :8081, one job worker
uv run pytest                # tests use the synthetic fixtures/ only
```

Losing the key file loses the data. In production the key is the Docker secret `/run/secrets/strydr_db_key`
(the default for `STRYDR_DB_KEY_FILE`). `strydr init --reset` replaces the user and token.

Regenerate fixtures: `python ../fixtures/generate_hae_export.py` (fully synthetic).

## Pointing HAE at Strydr (historical backfill)

Backfill over the LAN or Tailscale, not the tunnel (Cloudflare caps requests at 100 MB).

In Health Auto Export, add a REST API automation:

- URL: `http://<mac-lan-ip-or-tailscale-name>:8081/ingest/hae`
- Method: POST, format JSON
- Header: `Authorization: Bearer <token printed by strydr init>`
- Data: Workouts and the Health Metrics you want, with a date range covering your history.
  Batch requests if the export is large. Re-sending is safe: identical bodies and repeated workouts never duplicate.

HAE settings that matter: enable route data for workouts; keep "aggregate" at the default (day level).
Check progress at `GET /api/v1/sync-status` (log in at `POST /api/v1/auth/login` first).

## Settings added in slices 3-5

All of these live in the encrypted DB and are edited through the app-port API (`/api/v1`, session cookie).

**AI phrasing (off by default).** `PUT /settings/ai` with `{"provider": "nvidia", "api_key": "..."}`. AI stays off until a
key is set, and clearing it (`"api_key": ""`) switches it off again. The key is write-only: no endpoint returns it.
Defaults for `nvidia`: base URL `https://integrate.api.nvidia.com/v1` (OpenAI-compatible) and model
`nvidia/nemotron-3.5-lightning-30b-a3b` (a free hosted model; verified 2026-10-26, see `strydr/egress/providers.py`).
Use `"provider": "openai-compatible"` with your own `base_url` (https, or http on localhost) and `model` for anything else.
Only derived numbers and fixed words leave the server (`EgressPayload`); every reply is validated (no `!`, no banned
wording, at most 2 sentences, every number must belong to the fact) or the template wording is shown. The `phrase` job
runs only when no recompute or process_raw job is pending, with a 20 s timeout per call.

**Privacy zones.** `POST /privacy-zones` with `{"lat": ..., "lon": ..., "radius_m": 400}`; `GET /privacy-zones` lists
`{id, radius_m}`; `DELETE /privacy-zones/{id}`. The centre is write-only on purpose: it is accepted over the private app
port, stored with its randomized offset, and never returned by any endpoint, so a leaked session or cached response
cannot reveal home. Maps are clipped at recompute time and only the clipped geometry is served. Zones reduce the risk of
revealing home but do not remove it.

**Snapshots.** The `snapshot` job runs nightly at 02:30 in `home_tz` and writes an encrypted copy (SQLite online backup into a
destination keyed with the same key) to `$STRYDR_DATA_DIR/backups/strydr-YYYYMMDD.db`, keeping the newest 7.
`STRYDR_DATA_DIR` defaults to the directory of `STRYDR_DB_PATH`. A snapshot cannot be opened without the key.

**Other.** `PUT /settings/thresholds` overrides `config/thresholds.toml` values (validated; unknown keys are rejected).
`STRYDR_WEB_DIST` (default `/app/web/dist`) is the built SPA served by the app port; any non-`/api` GET falls back to
`index.html`. `GET /api/v1/health` is public and touches neither the DB nor its key. On start-up a stored
`adapter_version` older than `ADAPTER_VERSION` enqueues a `reparse` that rebuilds canonical rows from raw.
