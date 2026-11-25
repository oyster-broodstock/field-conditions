"""Observed rainfall at the site: NCEP Stage IV hourly analysis (radar + gauges, ~4 km grid),
read at the site's coordinates through the Iowa Environmental Mesonet. About 2 h behind real time.
"""
from __future__ import annotations

from config import RAIN_HOURS
from sources.common import get_json, iso, parse_iso, timedelta, utcnow

STAGE4 = "https://mesonet.agron.iastate.edu/json/stage4.py"


def fetch(site: dict) -> dict:
    now = utcnow()
    start = now - timedelta(hours=RAIN_HOURS)
    series = {}
    d = start.date()
    while d <= now.date():  # the service takes one UTC date per request
        url = f"{STAGE4}?lat={site['lat']}&lon={site['lon']}&valid={d.isoformat()}"
        for row in get_json(url).get("data", []):
            t = parse_iso(row["end_valid"])
            if start < t <= now and row["precip_in"] is not None:
                series[iso(t)] = {"t": iso(t), "precip_mm": round(row["precip_in"] * 25.4, 2)}
        d += timedelta(days=1)
    hourly = [series[k] for k in sorted(series)]

    def total(hours):
        if not hourly:
            return None
        end = parse_iso(hourly[-1]["t"])
        return round(sum(x["precip_mm"] for x in hourly if end - parse_iso(x["t"]) < timedelta(hours=hours)), 1)

    return {"source": "NCEP Stage IV precipitation analysis, via Iowa Environmental Mesonet",
            "source_url": "https://mesonet.agron.iastate.edu/rainfall/",
            "hourly": hourly, "through": hourly[-1]["t"] if hourly else None,
            "totals_mm": {f"h{h}": total(h) for h in (24, 72, 168)}, "units": {"precip_mm": "mm"}}
