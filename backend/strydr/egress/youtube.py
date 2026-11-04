"""YouTube import (AD-10 amendment): fetch one video's public title, description and caption transcript.

The fetch runs yt-dlp (on PATH, or STRYDR_YTDLP), because YouTube's caption links now return nothing to a plain request.
Only the video ID leaves the server: yt-dlp gets a youtube.com watch URL built from the checked ID, with config files,
cookies and cache off, so no identity is sent. The reply is public text; none of the runner's data is involved.
"""
import html
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlsplit

from strydr.egress.providers import EgressError

log = logging.getLogger("strydr.egress")

WATCH_URL = "https://www.youtube.com/watch"
LINK_HOSTS = frozenset({"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"})
FETCH_BUDGET_S = 18.0  # both yt-dlp runs; keeps the route under 65 s with the AI call
MAX_TRANSCRIPT = 12_000
MAX_DESCRIPTION = 2_000
MAX_TITLE = 200
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BASE_ARGS = ["--ignore-config", "--no-cookies", "--no-cookies-from-browser", "--no-cache-dir", "--no-playlist",
              "--no-warnings", "--socket-timeout", "10", "--skip-download"]
_UNAVAILABLE = ("private video", "video unavailable", "confirm your age", "age-restricted", "has been removed",
                "members-only", "this video is not available")

Runner = Callable[[list[str], float], subprocess.CompletedProcess]


class Unavailable(Exception):
    """The video is private, removed or age-restricted: YouTube would not serve its captions."""


@dataclass(frozen=True)
class VideoText:
    title: str
    description: str
    transcript: str


def video_id(url: str) -> str | None:
    """The video ID of a youtube.com watch, shorts or youtu.be link; None for anything else (checked before any fetch)."""
    if not isinstance(url, str):
        return None
    try:
        u = urlsplit(url.strip())
        host = (u.hostname or "").lower()
        port = u.port
    except ValueError:  # a malformed host or port
        return None
    if u.scheme not in ("http", "https") or host not in LINK_HOSTS or u.username or port not in (None, 80, 443):
        return None
    parts = [p for p in u.path.split("/") if p]
    if host.endswith("youtu.be"):
        cand = parts[0] if len(parts) == 1 else None
    elif u.path.rstrip("/") == "/watch":
        cand = dict(parse_qsl(u.query)).get("v")
    elif len(parts) == 2 and parts[0] == "shorts":
        cand = parts[1]
    else:
        cand = None
    return cand if cand and _ID.fullmatch(cand) else None


_TAG = re.compile(r"<[^>]*>")


def clean_vtt(vtt: str, limit: int = MAX_TRANSCRIPT) -> str:
    """Caption text only: no header, timings or cue markup; rolling auto-caption repeats collapsed; capped.

    A digit-only line is a cue number only when a timing line follows it; otherwise it is speech ("10"). Only
    consecutive identical lines, and a line that merely extends the one before it, collapse.
    """
    lines = [x.strip() for x in vtt.replace("\r", "").split("\n")]
    out: list[str] = []
    for i, line in enumerate(lines):
        if not line or line.startswith(("WEBVTT", "NOTE", "STYLE", "Kind:", "Language:")) or "-->" in line:
            continue
        if line.isdigit():
            nxt = next((x for x in lines[i + 1:] if x), "")
            if "-->" in nxt:
                continue
        text = " ".join(html.unescape(_TAG.sub("", line)).split())
        if not text or (out and text == out[-1]):
            continue
        if out and text.startswith(out[-1] + " "):  # a rolling caption growing in place
            out[-1] = text
            continue
        out.append(text)
    return " ".join(out)[:limit].rstrip()


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    exe = os.environ.get("STRYDR_YTDLP") or shutil.which("yt-dlp")
    if not exe:
        raise EgressError("yt-dlp missing")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)


def _pick_track(info: dict) -> tuple[str, bool] | None:
    """An English manual track first, then the English auto track (the original speech before a translation).

    Returns (language key, is_auto)."""
    manual = [k for k in (info.get("subtitles") or {}) if str(k).lower().split("-")[0] == "en"]
    if manual:
        return (min(manual, key=lambda k: (k != "en", k)), False)
    auto = info.get("automatic_captions") or {}
    for k in ("en-orig", "en"):
        if k in auto:
            return (k, True)
    return None


def fetch(vid: str, run: Runner | None = None) -> VideoText | None:
    """Title, description and transcript of one video; None when it has no English captions. Raises EgressError."""
    if not _ID.fullmatch(vid or ""):
        raise TypeError("youtube egress accepts only a video ID")
    run = run or _run
    url = f"{WATCH_URL}?v={vid}"
    deadline = time.monotonic() + FETCH_BUDGET_S

    def call(args: list[str]) -> subprocess.CompletedProcess:
        left = deadline - time.monotonic()
        if left <= 0:
            raise EgressError("fetch budget spent")
        r = run([*_BASE_ARGS, *args, "--", url], left)
        if r.returncode != 0:
            err = (r.stderr or "").lower()
            if any(m in err for m in _UNAVAILABLE):
                raise Unavailable(vid)
            log.warning("yt-dlp failed (%s): %s", r.returncode, (r.stderr or "").strip()[-300:])
            raise EgressError("yt-dlp failed")
        return r

    try:
        info = json.loads(call(["-J"]).stdout)
        if not isinstance(info, dict):
            raise ValueError("no video info")
        if info.get("availability") in ("private", "needs_auth", "subscriber_only", "premium_only"):
            raise Unavailable(vid)
        picked = _pick_track(info)
        if picked is None:
            return None
        lang, auto = picked
        with tempfile.TemporaryDirectory(prefix="strydr-yt-") as d:
            info_path = Path(d, "info.json")
            info_path.write_text(json.dumps(info), encoding="utf-8")
            call(["--load-info-json", str(info_path), "--write-auto-subs" if auto else "--write-subs",
                  "--sub-langs", lang, "--sub-format", "vtt", "-o", str(Path(d, "cap.%(ext)s"))])
            vtts = sorted(Path(d).glob("cap*.vtt"))
            transcript = clean_vtt(vtts[0].read_text(encoding="utf-8", errors="replace")) if vtts else ""
        if not transcript:
            return None
        return VideoText(title=str(info.get("title") or "")[:MAX_TITLE],
                         description=str(info.get("description") or "")[:MAX_DESCRIPTION],
                         transcript=transcript)
    except (Unavailable, EgressError):
        raise
    except subprocess.TimeoutExpired:
        raise EgressError("TimeoutExpired") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as e:
        raise EgressError(type(e).__name__) from None
