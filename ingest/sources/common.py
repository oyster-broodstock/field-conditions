"""Shared helpers: HTTP (with a per-run cache), time parsing, distance."""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from config import USER_AGENT

_cache: dict[str, object] = {}


def get_json(url: str, timeout: int = 40, accept: str = "application/json"):
    """GET and parse JSON. Cached for the run, so sites sharing a station fetch it once."""
    if url not in _cache:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _cache[url] = json.load(resp)
    return _cache[url]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def parse_valid_time(s: str) -> tuple[datetime, int]:
    """Parse an NWS validTime like '2026-09-24T18:00:00+00:00/PT6H' -> (start, hours)."""
    start, dur = s.split("/")
    m = _DUR.fullmatch(dur)
    if not m:
        raise ValueError(f"Unsupported ISO-8601 duration: {dur!r}")
    days, hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return parse_iso(start), max(days * 24 + hours + (1 if (minutes or seconds) else 0), 1)


def distance_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def r(v, d=2):
    return None if v is None else round(v, d)


__all__ = ["get_json", "utcnow", "iso", "parse_iso", "num", "parse_valid_time", "distance_km",
           "hour_floor", "r", "timedelta", "timezone", "datetime"]
