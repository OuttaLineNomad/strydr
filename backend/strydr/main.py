"""Entrypoint (AD-16): `strydr serve`, `strydr init` and the `relabel` maintenance command."""
import argparse
import asyncio
import contextlib
import getpass
import json
import logging
import signal
import sys
from pathlib import Path

import uvicorn

from strydr import logs
from strydr.api import create_app
from strydr.auth.service import create_user
from strydr.config import Config, read_db_key
from strydr.ingest import create_ingest_app, purge_incomplete
from strydr.jobs import Worker, reparse, scheduler
from strydr.store import migrate
from strydr.store.engine import make_engine

log = logging.getLogger("strydr")


def _engine(cfg: Config):
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(cfg.db_path, read_db_key(cfg.db_key_file))
    migrate.upgrade(engine)
    return engine


class _Server(uvicorn.Server):
    """Two servers share one loop, so signals are handled once by serve() instead of per server."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def serve(cfg: Config) -> None:
    logs.setup()
    engine = _engine(cfg)
    purge_incomplete(engine)
    key = read_db_key(cfg.db_key_file)
    worker = Worker(engine, cfg.home_tz, cfg.retry_backoff_s, db_key=key, backup_dir=cfg.data_dir / "backups")
    reparse.enqueue_if_stale(engine)  # AD-1: a newer ADAPTER_VERSION rebuilds canonical from raw

    def server(app, port: int) -> _Server:
        return _Server(uvicorn.Config(app, host=cfg.host, port=port, log_config=None, access_log=False))

    app_srv = server(create_app(engine, cfg.home_tz, cfg.web_dist), cfg.app_port)
    ingest_srv = server(create_ingest_app(engine), cfg.ingest_port)

    async def main() -> None:
        loop = asyncio.get_running_loop()

        def stop() -> None:
            app_srv.should_exit = ingest_srv.should_exit = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop)
        tick = asyncio.create_task(scheduler.run(engine, cfg.home_tz))
        try:
            await asyncio.gather(app_srv.serve(), ingest_srv.serve())
        finally:
            tick.cancel()

    worker.start()  # AD-16: exactly one worker thread, started here and never from a lifespan
    log.info("strydr serving: app :%d, ingest :%d", cfg.app_port, cfg.ingest_port)
    try:
        asyncio.run(main())
    finally:
        worker.stop()


def init(cfg: Config, username: str, password_file: Path | None, reset: bool) -> None:
    engine = _engine(cfg)
    if password_file:
        password = password_file.read_text().strip()
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            raise SystemExit("passwords do not match")
    if len(password) < 8:
        raise SystemExit("password must be at least 8 characters")
    token = create_user(engine, username, password, reset)
    print(f"User '{username}' created.\nIngest token (shown once; set as the HAE bearer token):\n{token}")


def openapi(out: Path) -> None:
    """Write the app-port OpenAPI schema (AD-13). Needs no DB or key."""
    out.write_text(json.dumps(create_app(None).openapi(), indent=2, sort_keys=True) + "\n")


def cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="strydr")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run app (:8080), ingest (:8081) and the job worker")
    pi = sub.add_parser("init", help="create the single user and print the ingest token")
    pi.add_argument("--username", default="runner")
    pi.add_argument("--password-file", type=Path, help="read the password from a file instead of prompting")
    pi.add_argument("--reset", action="store_true", help="replace the existing user and token")
    pr = sub.add_parser("relabel", help="correct the type of past workouts (e.g. walks that were runs)")
    pr.add_argument("--from", dest="src", required=True, choices=("run", "walk", "hike", "strength"))
    pr.add_argument("--to", dest="dst", required=True, choices=("run", "walk", "hike"))
    pr.add_argument("--through", required=True, help="last local date included, YYYY-MM-DD")
    po = sub.add_parser("openapi", help="write the OpenAPI schema for the frontend type generator")
    po.add_argument("--out", type=Path, default=Path("openapi.json"))
    args = p.parse_args(argv)
    if args.cmd == "openapi":
        return openapi(args.out)
    cfg = Config()
    if args.cmd == "serve":
        serve(cfg)
    elif args.cmd == "relabel":
        from strydr.relabel import relabel

        n = relabel(_engine(cfg), args.src, args.dst, args.through, cfg.home_tz)
        print(f"Relabelled {n} {args.src} workout(s) through {args.through} as {args.dst}. A recompute is queued.")
    else:
        init(cfg, args.username, args.password_file, args.reset)


if __name__ == "__main__":
    cli(sys.argv[1:])
