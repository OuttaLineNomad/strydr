# Deploying Strydr with Docker (x86_64 Linux)

Two containers: `strydr` (app `:8080`, ingest `:8081`) and `cloudflared` (tunnel to `:8081` only).
Run every command from the repo root unless noted.

## 1. Install Docker (Debian/Ubuntu)

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # log out and back in
docker compose version
```

## 2. Create the secrets (never commit these; `secrets/` is gitignored)

```sh
mkdir -p secrets && chmod 700 secrets
openssl rand -hex 32 > secrets/strydr_db_key          # 64 hex characters
chmod 644 secrets/strydr_db_key                        # the container runs as uid 10001; the 700 dir protects it
```

Back this key up somewhere safe and separate from the data. **Losing it loses all data.**
The Cloudflare credentials file comes from step 5.

## 3. Build on the XPS

```sh
git clone <repo> strydr && cd strydr
export TZ=Europe/London         # optional; or put TZ=... in .env (compose default is UTC)
docker compose build strydr
```

Build on the XPS itself so the image matches its architecture (sqlcipher3 needs a matching wheel).

## 4. Initialise (create the user and ingest token)

```sh
docker compose run --rm strydr init
```

Prompts for a password (min 8 chars) and prints the ingest token once. Save it; it is the HAE bearer token.
`init --reset` replaces the user and token. Then start everything after step 5, or just the app with
`docker compose up -d strydr`.

## 5. Cloudflare tunnel

On any machine with `cloudflared` installed:

```sh
cloudflared tunnel login
cloudflared tunnel create strydr          # prints the UUID and writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns strydr strydr-ingest.example.com
```

On the XPS:

```sh
cp ~/.cloudflared/<UUID>.json secrets/cloudflared-credentials.json
chmod 644 secrets/cloudflared-credentials.json
cp cloudflared/config.yml.example cloudflared/config.yml
# edit: uncomment `tunnel:` and the hostname rule, fill in UUID and hostname
docker compose up -d
```

The only ingress rule is `hostname -> http://strydr:8081`, then a `http_status:404` catch-all.
Never route a hostname to `:8080`; the dashboard stays LAN/Tailscale only (AD-11).

## 6. Tailscale on the host

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

The app is then at `http://<xpss-tailscale-name>:8080` from your devices. Do not use `tailscale funnel`.
Keep `8080`/`8081` closed at the router/firewall (no port forwards).

## 7. Point Health Auto Export at Strydr

REST API automation, POST, JSON, header `Authorization: Bearer <ingest token>`.

- **Routine syncs:** `https://strydr-ingest.example.com/ingest/hae` (tunnel). Keep each batch under 100 MB.
- **Historical backfill:** `http://<xps-lan-ip-or-tailscale-name>:8081/ingest/hae`. Cloudflare caps tunnel
  request bodies at 100 MB, so large backfills must use the LAN/Tailscale URL.

## 8. Backups

The `snapshot` job writes encrypted copies (same key) to `/data/backups/strydr-YYYYMMDD.db`, keeping 7.
These live on the same disk, so copy them off the machine regularly:

```sh
docker compose cp strydr:/data/backups ./backups-$(date +%F)
# or: sudo rsync -a "$(docker volume inspect strydr_strydr_data -f '{{.Mountpoint}}')/backups/" user@nas:/path/
```

Restoring needs the DB key. Store the key separately from the backups.

## 9. Upgrades

```sh
git pull
docker compose build
docker compose up -d       # recreates changed containers; migrations run on start
docker image prune -f
```

Bump the `cloudflare/cloudflared` tag in `compose.yaml` deliberately. Take a backup copy before upgrading.

## Health

The app port serves the built SPA from `/app/web/dist`. Docker's healthcheck calls the public `GET /api/v1/health`, which needs no DB access.
