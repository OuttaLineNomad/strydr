# Troubleshooting and FAQ

## Syncing

**Health Auto Export says the request failed.**
- `401`: the token is wrong. The header must be exactly `Authorization` with the value `Bearer <token>` (with the space).
  Lost the token? `strydr init --reset` issues a new one (and replaces the user).
- `413` or a timeout through the tunnel: Cloudflare caps a request at 100 MB. Do big backfills on your home network or
  Tailscale, or split them into smaller date ranges.
- Cannot connect: check that the phone is on the same network, that port `8081` is allowed by the server's firewall, and
  that the server's address has not changed. On Windows, run the installer again to update **Strydr details.txt** with
  the new address.

**Syncs worked, then stopped.** Your router may have given the server a new address. Give it a fixed address (a DHCP
reservation) or use its Tailscale name.

**The dashboard says "Stale".** No new data has arrived for more than 7 days. Check that the automations are still on in
Health Auto Export.

**A run shows no map.** The workout came without route data. In Health Auto Export, include route data for workouts, and
re-send that date range; the richer copy replaces the old one. Indoor runs have no route.

**Heart-rate zones look blocky.** Older exports are per minute. Choose **Seconds** for time grouping in Health Auto
Export and re-send; Strydr keeps the finer copy.

**I see the same workout twice.** Re-sends and HAE-plus-Apple copies are merged when their start times are within 60
seconds and the type matches. If you changed a workout's type in one copy, the other may not match; open an issue with
the two dates and types.

## Apple Health import

**The upload is slow or stops.** Exports can be several gigabytes. Upload from a computer on the same network as the
server rather than over a slow link. The limit is 4 GB.

**The import failed.** Settings shows the error type. Strydr checks the whole file before writing, so nothing partial is
left behind; export again from the Health app and retry.

## Numbers

**My zones are wrong.** Set your own **HRmax** in Settings. Without one, Strydr uses the age estimate
(`208 − 0.7 × age`), which can be well off for an individual.

**A walk was counted as a run (or the reverse).** Change the type on the workout page. For many at once, use
`strydr relabel` ([CLI](configuration.md#cli)).

**Pace looks slow on a hot or hilly day.** Look at **Conditions** and the **GAP** column on the run. Heat-adjusted and
grade-adjusted paces estimate how the same effort would have looked on a cool, flat day.

**Some insights never appear.** Many need history: 21 days for resting heart rate, 40 for HRV, 28 days of load for rest-day
and monotony checks, and enough runs on each side for the comparison insights. See the [Insights reference](insights.md).

**An insight is not useful to me.** Give it a thumbs down, or change its threshold in **Settings → Advanced:
thresholds**. `no-rest-day` can be switched off entirely.

## Server

**I lost the database key.** The data and all snapshots cannot be decrypted. Start again with a new key and re-import.
This is why the key should be backed up separately.

**Where is my data?**
- Docker: the volume `strydr_strydr_data` (`/data` in the container); snapshots in `/data/backups`.
- Windows: the same Docker volume; the app files and the key copy are in `%LOCALAPPDATA%\Strydr`.
- From source: wherever `STRYDR_DB_PATH` points.

**How do I see what the server is doing?** `docker compose logs -f strydr`. Each line is JSON with a level, a logger
(`strydr.ingest`, `strydr.jobs`, `strydr.egress`) and a message such as `recompute as_of=2026-11-04: generation 5
published`.

**YouTube import fails.** YouTube changes often. Update yt-dlp: in development `cd backend && uv lock --upgrade-package
yt-dlp && uv sync`; in Docker rebuild the image after that. Repeated fetches of one video can be rate-limited by YouTube
for a while. Import also needs AI phrasing on.

## FAQ

**Does Strydr work without an Apple Watch?** It reads Apple Health's formats, so any device that writes workouts with
heart rate and routes to Apple Health should work. It is built and tested around Apple Watch data.

**Android, Garmin, Strava?** Not today. Sources are separate adapters (`backend/strydr/sources/`), so a new source is a
contained piece of work. Open an issue if you want to help.

**Can several people use one server?** Not yet. Strydr has one user per instance; run one instance per person.

**Is there a hosted version?** No. Strydr is self-hosted by design.

**Does it predict race times?** No. Predictions from short recreational runs are not honest, so Strydr leaves them out.

**Is this medical advice?** No. Strydr describes patterns in your training data.
