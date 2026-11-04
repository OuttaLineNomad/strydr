# Installation

Strydr runs as one process with two ports:

| Port | What | Who should reach it |
|---|---|---|
| `8080` | The web app and its API (`/api/v1`) | Your own devices only: home network or Tailscale |
| `8081` | The ingest endpoint for Health Auto Export (`/ingest/hae`) | Your iPhone: home network, Tailscale, or an optional Cloudflare tunnel |

Never expose `8080` to the internet. Only the ingest port is meant to sit behind a tunnel, and it accepts nothing
without the bearer token.

- [Windows](#windows)
- [Docker (Linux)](#docker-linux)
- [Remote syncs with a Cloudflare tunnel](#remote-syncs-with-a-cloudflare-tunnel)
- [Tailscale](#tailscale)
- [Without Docker](#without-docker)
- [Backups](#backups)
- [Upgrades](#upgrades)
- [Uninstalling](#uninstalling)

## Windows

For Windows 10 (22H2) and Windows 11, 64-bit, with an administrator account.

1. Download [Install Strydr.cmd](https://raw.githubusercontent.com/OuttaLineNomad/strydr/main/install/windows/Install%20Strydr.cmd)
   and double-click it.
2. Approve the administrator prompt. The installer turns on WSL 2, installs Docker Desktop, restarts once and carries on
   after you sign in again.
3. When it finishes, Notepad opens **Strydr details.txt** with the address, your username and password, the Health Auto
   Export URL and token, and where the database key is kept.

Run the installer again to update; your data, password and token stay the same. Full details, including what it changes
on the PC: [install/windows/README.md](../install/windows/README.md).

## Docker (Linux)

Works on x86_64 and arm64. Run everything from the repository root.

```sh
# 1. Docker (Debian/Ubuntu)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"            # log out and back in

# 2. Get Strydr and create the database key (never commit it; secrets/ is gitignored)
git clone https://github.com/OuttaLineNomad/strydr.git && cd strydr
mkdir -p secrets && chmod 700 secrets
openssl rand -hex 32 > secrets/strydr_db_key
chmod 644 secrets/strydr_db_key             # the container runs as uid 10001; the 700 folder protects it

# 3. Build on the server itself, so the image matches its CPU
export TZ=America/New_York                  # optional; or TZ=... in .env (default UTC)
docker compose build strydr

# 4. Create your user; prints the ingest token once
docker compose run --rm strydr init

# 5. Start it
docker compose up -d strydr
```

Open `http://<server-ip>:8080` and sign in. Then [point Health Auto Export at it](importing-data.md#health-auto-export).

> **Back up `secrets/strydr_db_key` now**, somewhere other than this server. Without it the database and every snapshot
> are unreadable.

Docker keeps the data in the named volume `strydr_strydr_data` (mounted at `/data`). A health check calls the public
`GET /api/v1/health`, which touches neither the database nor the key.

The step-by-step version with more notes is in [deploy/README.md](../deploy/README.md).

## Remote syncs with a Cloudflare tunnel

Without a tunnel, your iPhone syncs only when it is on your home network (or on Tailscale). A Cloudflare tunnel lets it
sync from anywhere, and it exposes **only** the ingest port.

```sh
# On any machine with cloudflared installed
cloudflared tunnel login
cloudflared tunnel create strydr                       # writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns strydr strydr-ingest.example.com

# On the server
cp ~/.cloudflared/<UUID>.json secrets/cloudflared-credentials.json
chmod 644 secrets/cloudflared-credentials.json
cp cloudflared/config.yml.example cloudflared/config.yml   # fill in the UUID and hostname
docker compose --profile tunnel up -d
```

The only ingress rule is `hostname → http://strydr:8081`, followed by a `404` catch-all. Cloudflare caps request bodies
at 100 MB, so do large historical backfills over the LAN or Tailscale, and use the tunnel URL for routine syncs.

## Tailscale

Tailscale is the easiest way to open the dashboard away from home without exposing anything:

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Then use `http://<server-tailscale-name>:8080` from your phone or laptop. Do not use `tailscale funnel`, and keep `8080`
and `8081` closed on your router (no port forwards).

## Without Docker

On macOS or Linux you can run Strydr straight from the source with uv. This is also the development setup:

```sh
cd backend && uv sync
mkdir -p ~/strydr-data
openssl rand -hex 32 > ~/strydr-data/db.key && chmod 600 ~/strydr-data/db.key
export STRYDR_DB_KEY_FILE=~/strydr-data/db.key STRYDR_DB_PATH=~/strydr-data/strydr.db STRYDR_HOME_TZ=America/New_York
uv run strydr init
(cd ../web && npm ci && npm run build)
STRYDR_WEB_DIST=$PWD/../web/dist uv run strydr serve
```

See [Development](development.md) for the hot-reload frontend and tests.

## Backups

Every night at 02:30 (home time zone) the `snapshot` job writes an encrypted copy of the database to
`<data dir>/backups/strydr-YYYYMMDD.db` and keeps the newest seven. Snapshots use the same key, so they are safe to copy
to a NAS or cloud drive, and useless without the key.

The snapshots sit on the same disk as the database, so copy them off the machine regularly:

```sh
docker compose cp strydr:/data/backups ./backups-$(date +%F)
```

To restore, stop Strydr, put the snapshot in place of `strydr.db` (removing any `strydr.db-wal` and `strydr.db-shm`),
and start it with the same key.

## Upgrades

```sh
git pull
docker compose build
docker compose up -d            # add --profile tunnel if you use the tunnel
docker image prune -f
```

Database migrations run automatically on start. If a new version parses source data differently, Strydr rebuilds its
tables from the stored raw payloads by itself (a `reparse` job), so you never need to re-import. Copy a snapshot off the
machine before a big upgrade.

On Windows, run the installer again.

## Uninstalling

```sh
docker compose down -v          # -v deletes the data volume: all Strydr data
```

On Windows: `cd $env:LOCALAPPDATA\Strydr\app; docker compose down -v`, then delete `%LOCALAPPDATA%\Strydr`.
