"""YouTube import (AD-10 amendment): fetch one video's public title, description and caption transcript.

Only the video ID leaves the server, as a GET to youtube.com (and to the caption host the page names, which must also
be on youtube.com). No cookies or identity are sent, apart from a fixed consent cookie if YouTube shows its consent
page. Redirects are off. The reply is public text; none of the runner's data is involved.
"""
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from strydr.egress.providers import EgressError

log = logging.getLogger("strydr.egress")

WATCH_HOST = "www.youtube.com"
WATCH_URL = f"https://{WATCH_HOST}/watch"
LINK_HOSTS = frozenset({"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"})
CONSENT_COOKIE = "SOCS=CAI; CONSENT=YES+1"  # fixed value: no identity
FETCH_CALL_S = 10.0  # each request; the whole fetch is capped by FETCH_BUDGET_S so the route stays under 65 s with the AI call
FETCH_BUDGET_S = 15.0
MAX_TRANSCRIPT = 12_000
MAX_DESCRIPTION = 2_000
MAX_TITLE = 200
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; strydr)", "Accept-Language": "en-US,en;q=0.9"}


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


def _player_response(page: str) -> dict | None:
    m = re.search(r"ytInitialPlayerResponse\s*=\s*", page)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(page, m.end())
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _pick_track(tracks: list) -> str | None:
    """An English manual track first, then English auto (asr). Returns its base URL."""
    en = [t for t in tracks if isinstance(t, dict) and str(t.get("languageCode", "")).lower().startswith("en")
          and isinstance(t.get("baseUrl"), str)]
    for t in sorted(en, key=lambda t: t.get("kind") == "asr"):
        return t["baseUrl"]
    return None


def _caption_url(base: str) -> str:
    u = urlsplit(base)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not (host == "youtube.com" or host.endswith(".youtube.com")):
        raise ValueError("caption host is not on youtube.com")
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k != "fmt"] + [("fmt", "vtt")]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), ""))


def _get(c: httpx.Client, deadline: float, url: str, **kw) -> httpx.Response:
    """One request inside the fetch's total budget. The jar is emptied first: YouTube's Set-Cookie is never replayed."""
    left = deadline - time.monotonic()
    if left <= 0:
        raise httpx.ReadTimeout("fetch budget spent")
    c.cookies.clear()
    return c.get(url, timeout=min(FETCH_CALL_S, left), **kw)


def _get_page(c: httpx.Client, deadline: float, vid: str) -> dict | None:
    cookie = None
    for _ in range(2):
        headers = _HEADERS | ({"Cookie": cookie} if cookie else {})
        r = _get(c, deadline, WATCH_URL, params={"v": vid}, headers=headers)
        if r.is_redirect:  # the consent page: try once more with the fixed consent cookie
            if cookie:
                return None
            cookie = CONSENT_COOKIE
            continue
        r.raise_for_status()
        pr = _player_response(r.text)
        if pr is not None:
            return pr
        if cookie:
            return None
        cookie = CONSENT_COOKIE  # a consent interstitial served inline
    return None


def fetch(vid: str, transport: httpx.BaseTransport | None = None) -> VideoText | None:
    """Title, description and transcript of one video; None when it has no English captions. Raises EgressError."""
    if not _ID.fullmatch(vid or ""):
        raise TypeError("youtube egress accepts only a video ID")
    try:
        deadline = time.monotonic() + FETCH_BUDGET_S
        with httpx.Client(timeout=httpx.Timeout(FETCH_CALL_S), transport=transport, follow_redirects=False) as c:
            pr = _get_page(c, deadline, vid)
            if pr is None:
                raise ValueError("no player response")
            status = (pr.get("playabilityStatus") or {}).get("status")
            if status is not None and status != "OK":
                raise Unavailable(str(status))
            details = pr.get("videoDetails") or {}
            tracks = (((pr.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks")) or []
            base = _pick_track(tracks) if isinstance(tracks, list) else None
            if base is None:
                return None
            r = _get(c, deadline, _caption_url(base), headers=_HEADERS)
            r.raise_for_status()
            transcript = clean_vtt(r.text)
        if not transcript:
            return None
        return VideoText(title=str(details.get("title") or "")[:MAX_TITLE],
                         description=str(details.get("shortDescription") or "")[:MAX_DESCRIPTION],
                         transcript=transcript)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError, RecursionError) as e:
        raise EgressError(type(e).__name__) from None
