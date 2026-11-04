#!/usr/bin/env bash
# Rebuild the synthetic demo and retake every docs screenshot into docs/images/ (WebP).
#
#   CHROME_PATH=/path/to/chrome fixtures/demo/make-screenshots.sh
#
# Needs: uv, node, npm, curl, ImageMagick (magick) and cwebp. Uses a throwaway key and database in a temp folder and a
# server on 127.0.0.1:8090/8091 only. The web app is built first. Weather lookup is turned on for the demo, which sends
# grid cells around Central Park to Open-Meteo; map tiles come from OpenFreeMap.
set -euo pipefail

: "${CHROME_PATH:?set CHROME_PATH to a Chrome or Chromium binary}"
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
IMAGES="$ROOT/docs/images"
WORK=$(mktemp -d)
export DEMO_URL=http://127.0.0.1:8090 DEMO_PASSWORD=demo-password-1 CHROME_PATH
export STRYDR_HOST=127.0.0.1 STRYDR_APP_PORT=8090 STRYDR_INGEST_PORT=8091 STRYDR_HOME_TZ=America/New_York
export STRYDR_DB_KEY_FILE="$WORK/db.key" STRYDR_DB_PATH="$WORK/strydr.db" STRYDR_WEB_DIST="$ROOT/web/dist"

SERVER=
cleanup() { [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

echo "== data and server"
python3 -I "$HERE/generate.py" "$WORK/out"
(cd "$ROOT/web" && npm run build >/dev/null)
(cd "$HERE" && npm install --silent)
openssl rand -hex 32 > "$WORK/db.key"
printf '%s\n' "$DEMO_PASSWORD" > "$WORK/pw"
cd "$ROOT/backend"
uv sync -q
TOKEN=$(.venv/bin/strydr init --username demo --password-file "$WORK/pw" | tail -1)
.venv/bin/strydr serve > "$WORK/serve.log" 2>&1 &  # not through uv run, so the kill below reaches the server
SERVER=$!
until curl -sf "$DEMO_URL/api/v1/health" >/dev/null; do sleep 1; done

for f in "$WORK"/out/w*.json "$WORK/out/metrics.json"; do
  curl -sf -o /dev/null -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    --data-binary @"$f" http://127.0.0.1:8091/ingest/hae
done
uv run python "$HERE/seed.py" "$WORK/out"

echo "== waiting for weather"
until uv run python - <<'EOF'
import os, sys, httpx
c = httpx.Client(base_url=os.environ["DEMO_URL"] + "/api/v1", timeout=30)
c.post("/auth/login", json={"username": "demo", "password": os.environ["DEMO_PASSWORD"]})
w = c.get("/settings/weather").json()
sys.exit(0 if w["fetched"] + w["unavailable"] + w["skipped"] >= 71 else 1)
EOF
do sleep 5; done
sleep 20  # the recompute after the last weather fetch

echo "== screenshots"
cd "$HERE"
RUN=$(python3 -c "import sys; sys.path.insert(0, '.'); from generate import wid; print(wid('2026-10-31-long'))")
ROUTE=$(python3 -c "import sys; sys.path.insert(0, '.'); from generate import wid; print(wid('2026-06-18-loop'))")
SHOTS="$WORK/shots"
node shoot.mjs "$SHOTS/desktop" 1440 900 dark \
  'dashboard=/' 'dashboard-full=/=full' 'runs=/runs' "run-detail=/runs/$RUN" "run-detail-full=/runs/$RUN=full" \
  'activities=/activities' 'routes=/runs/routes' "route-detail=/runs/routes/$ROUTE=full" 'weeks=/weeks' \
  'week-detail=/weeks/2026-W44=full' 'calendar=/calendar?month=2026-10' 'recap-year=/recap?period=2026=full' \
  'workouts=/workouts=full' 'workout-plan=/workouts/1=full' 'workout-edit=/workouts/1/edit=full' \
  'session-summary=/workouts/sessions/18=full' 'settings=/settings=full' 'login=/login'
node shoot.mjs "$SHOTS/light" 1440 900 light 'dashboard=/' "run-detail=/runs/$RUN"
SCALE=3 node shoot.mjs "$SHOTS/phone" 390 844 dark \
  'dashboard=/' "run-detail=/runs/$RUN" 'workouts=/workouts' 'live=/workouts/1/run' 'weeks=/weeks'

echo "== converting"
mkdir -p "$IMAGES"
for f in "$SHOTS"/desktop/*.png; do
  n=$(basename "$f" .png)
  case $n in *-full|route-detail|week-detail|recap-*|workouts|workout-*|session-summary|settings|calendar) W=1440;; *) W=1600;; esac
  magick "$f" -resize "${W}x" "$WORK/tmp.png" && cwebp -quiet -q 80 "$WORK/tmp.png" -o "$IMAGES/$n.webp"
done
for f in "$SHOTS"/light/*.png; do cwebp -quiet -q 80 -resize 1600 0 "$f" -o "$IMAGES/light-$(basename "$f" .png).webp"; done
for n in dashboard run-detail live weeks; do cwebp -quiet -q 80 -resize 780 0 "$SHOTS/phone/$n.png" -o "$IMAGES/phone-$n.webp"; done
(cd "$SHOTS/phone" && magick dashboard.png run-detail.png live.png workouts.png -resize 780x -background none \
  -splice 40x0 +append -chop 40x0 "$WORK/strip.png")
cwebp -quiet -q 80 -alpha_q 90 "$WORK/strip.png" -o "$IMAGES/phone-strip.webp"
echo "done: $(ls "$IMAGES" | wc -l | tr -d ' ') images in docs/images"
