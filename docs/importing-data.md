# Importing data

Strydr reads Apple Health data from two sources. You can use either or both, and the same workout arriving from both is
stored once.

| | Health Auto Export | Apple Health export |
|---|---|---|
| Cost | iOS app; REST API automations may need its paid upgrade | Free, built into iOS |
| How | Automations push JSON to the ingest port | You upload `export.zip` in Settings |
| When | On a schedule, automatically | Whenever you export |
| Best for | Day-to-day syncing | Trying Strydr, or loading years of history at once |

- [Health Auto Export](#health-auto-export)
- [Apple Health export](#apple-health-export)
- [What Strydr reads](#what-strydr-reads)
- [Duplicates and re-sends](#duplicates-and-re-sends)
- [Checking a sync](#checking-a-sync)
- [Fixing what came in](#fixing-what-came-in)

## Health Auto Export

Health Auto Export (HAE) is an iOS app that sends Apple Health data to a URL. Strydr accepts its JSON format at
`POST /ingest/hae` on port `8081`.

### Set up the automations

Make **two** REST API automations, one for **Workouts** and one for **Health Metrics**. For each:

| Setting | Value |
|---|---|
| Automation type | REST API |
| URL | `http://<server-lan-ip-or-tailscale-name>:8081/ingest/hae` (or your tunnel URL, see below) |
| Method | POST |
| Header | `Authorization` = `Bearer <ingest token>` |
| Export format | JSON |
| Workouts | Include heart rate and route data. Choose **Seconds** for time grouping if offered |
| Health Metrics | The metrics you want (see [What Strydr reads](#what-strydr-reads)); keep "aggregate" at the default day level |

The ingest token is the one printed by `strydr init` (or shown in **Strydr details.txt** on Windows). Run
`strydr init --reset` to issue a new one; that also replaces the user.

### Backfill your history first

Before turning on the schedule, run each automation once by hand with a date range that covers your history.

- Do the backfill over your **home network or Tailscale**, not the Cloudflare tunnel: Cloudflare caps a request at
  100 MB.
- If the export is large, split it into batches (for example one per few months). Each request is stored and processed
  on its own.
- Re-sending a range is safe. See [Duplicates and re-sends](#duplicates-and-re-sends).

### Routine syncs

Then let the automations run on a schedule. On your home network the phone reaches `http://<server>:8081`. To sync from
anywhere, set up the [Cloudflare tunnel](installation.md#remote-syncs-with-a-cloudflare-tunnel) and use
`https://<your-ingest-hostname>/ingest/hae`. Missed syncs catch up the next time the automation runs.

### Heart-rate resolution

Strydr keeps every heart-rate sample at the resolution it arrives in. HAE exports at per-minute grouping by default;
with **Seconds** it sends a reading every few seconds, which gives more accurate zones, training load and drift. Strydr
weights each sample by the time it covers, so per-minute and per-second data can be mixed in one history.

## Apple Health export

The free path. It needs no extra app.

1. On your iPhone, open **Health**, tap your profile picture, then **Export All Health Data**. This can take a few
   minutes and produces `export.zip`.
2. Send the file to the computer you browse Strydr on (AirDrop, Files, a cable).
3. In Strydr, open **Settings → Import from Apple Health**, choose `export.zip` and upload it.

Uploads up to 4 GB are accepted. The file goes only to your server and is stored encrypted. Strydr checks the whole
export before writing anything, so a damaged file never leaves a half-finished import. Settings shows the progress and,
when done, how many workouts, metrics and sleep nights were read, how many matched workouts already stored from HAE,
and the date range covered.

The export also carries your date of birth and sex if you have set them in Health. Strydr uses them only as profile
defaults, and anything you set in Settings wins.

## What Strydr reads

**Workouts**

| Apple type | In Strydr |
|---|---|
| Running | Run |
| Walking | Walk |
| Hiking | Hike |
| Functional and traditional strength training | Strength (matched to [home workouts](home-workouts.md)) |

Other types, such as cycling, are skipped. For each workout Strydr keeps the route, heart rate, steps, the watch's
splits, elevation, temperature and humidity, effort score, and the active time with pauses removed.

**Daily metrics** used in analysis: resting heart rate, heart-rate variability (SDNN), sleep (stages, in bed, asleep),
step count and body weight. Others you export are stored but not used yet.

**Data quality.** Impossible readings (heart rate outside 30 to 230 bpm, GPS jumps faster than 12 m/s) are dropped and
counted, never silently smoothed. The counts are kept with the workout.

## Duplicates and re-sends

You can send the same data as many times as you like:

- **Identical requests** are recognised and ignored.
- **The same workout again** (same ID) is stored once. If the new copy is richer, for example it now has the route or
  more heart-rate samples, it replaces the old one; otherwise the stored copy stays.
- **HAE and Apple copies** of one workout are matched by type and a start time within 60 seconds, and merged into one.

Strydr always keeps the raw payloads. When a new version of Strydr parses data differently, it rebuilds everything from
them by itself, so you never need to re-export.

## Checking a sync

- The dashboard header shows **Last synced** with the time of the last processed payload. If nothing has arrived for a
  week, it says the data is stale.
- `GET /api/v1/sync-status` (signed in) returns the same as JSON.
- The server log lists each accepted payload: `payload 12 accepted (528709 bytes)`.

A payload that fails to parse is kept and retried; check the log for the error class.

## Fixing what came in

| Problem | Fix |
|---|---|
| A workout has the wrong type (a walk that was really a run) | Open it and pick **Run**, **Walk** or **Hike** under **About this workout** |
| Many past workouts have the wrong type | `strydr relabel --from walk --to run --through 2026-10-28` (see [Configuration](configuration.md#cli)) |
| You carried a pack, vest or child | Set **Extra weight carried** on the workout. Carried runs are compared only with other carried runs |
| Sleep hours are wrong for a night | On the run, under **Sleep the night before**, tap **Correct hours** |
| Two repeated routes were grouped wrongly | On the route page, **Fix the grouping**: join or split runs |

Type fixes and corrections survive re-sends and reparses.
