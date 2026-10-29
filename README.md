# Strydr

Self-hosted running analytics for Apple Watch runners. Strydr takes your workouts and health metrics from
Apple Health and explains each run in context: heat, hills, sleep, resting heart rate and HRV, and the week
around it. Everything lives in one encrypted database on your own machine.

- **Runs:** splits, pace, heart rate (kept at full resolution), elevation, grade-adjusted pace, weather and
  pause-aware heart-rate zones.
- **Training:** weekly load, a training calendar, personal records, and repeated routes with a map of every run.
- **Insights:** rule-based observations about your training, with an optional short AI summary per run.
  Only preformatted, location-free numbers ever leave the machine, and only if you turn AI on.
- **Privacy:** SQLCipher-encrypted storage, privacy zones that clip routes near home, and no telemetry.

## Getting data in

- **Health Auto Export** (iOS app): REST API automations push workouts and health metrics to the ingest
  port. See [backend/README.md](backend/README.md#pointing-hae-at-strydr-historical-backfill).
- **Apple Health export** (free): upload `export.zip` from the Health app in Settings, Import.

## Running it

- Development (macOS or Linux): [backend/README.md](backend/README.md), then `cd web && npm install && npm run dev`.
- Windows, one step: [install/windows/README.md](install/windows/README.md) installs Docker, builds and starts
  Strydr, and prints the sign-in and sync token.
- Docker on Linux, with an optional Cloudflare tunnel for remote syncs: [deploy/README.md](deploy/README.md).

The stack is Python 3.14 (FastAPI, SQLAlchemy, SQLCipher, uv) and Vue 3 with TypeScript (Vite, MapLibre).
Tests run on synthetic fixtures only (`fixtures/`): `cd backend && uv run pytest`, `cd web && npm test`.

Strydr describes training patterns. It is not medical advice.

## License

[MIT](LICENSE)
