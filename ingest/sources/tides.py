"""NOAA CO-OPS tide predictions (metres above MLLW).

Most stations near the sites are subordinate stations, for which NOAA publishes only
high/low times and heights. The curve between them is a cosine interpolation, the
standard approximation.
"""
from __future__ import annotations

import math

from config import APP, TIDE_DAYS
from sources.common import datetime, get_json, iso, timedelta, timezone, utcnow

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


def _hilo(station: str, begin: datetime, hours: int) -> list[dict]:
    url = (f"{API}?station={station}&product=predictions&datum=MLLW&units=metric&time_zone=gmt"
           f"&format=json&interval=hilo&begin_date={begin:%Y%m%d}&range={hours}&application={APP}")
    data = get_json(url)
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "NOAA error"))
    return [{"t": iso(datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)),
             "v": round(float(p["v"]), 2), "type": p["type"]} for p in data["predictions"]]


def curve(hilo: list[dict], start: datetime, end: datetime, step_min: int = 20) -> list[list]:
    pts = [(datetime.fromisoformat(h["t"].replace("Z", "+00:00")), h["v"]) for h in hilo]
    out, t, i = [], start, 0
    while t <= end and len(pts) > 1:
        while i < len(pts) - 2 and pts[i + 1][0] <= t:
            i += 1
        (t1, h1), (t2, h2) = pts[i], pts[i + 1]
        if t1 <= t <= t2:
            frac = (t - t1).total_seconds() / (t2 - t1).total_seconds()
            out.append([iso(t), round(h1 + (h2 - h1) * (1 - math.cos(math.pi * frac)) / 2, 2)])
        t += timedelta(minutes=step_min)
    return out


def fetch(site: dict) -> dict:
    st = site["tide"]
    now = utcnow()
    begin = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hilo = _hilo(st["id"], begin, 24 * (TIDE_DAYS + 1))
    start = hour_floor_12(now)
    return {"station": st, "datum": "MLLW", "units": "m",
            "source": "NOAA CO-OPS tide predictions",
            "source_url": f"https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id={st['id']}",
            "hilo": hilo, "curve": curve(hilo, start, start + timedelta(days=4))}


def hour_floor_12(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=12)
