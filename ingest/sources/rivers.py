"""River discharge from USGS (freshet driver for low-salinity events)."""
from __future__ import annotations

from config import RIVER_DAYS
from sources.common import get_json, iso, num, parse_iso, r

API = "https://waterservices.usgs.gov/nwis/iv/"
CFS_TO_CMS = 0.0283168


def fetch(site: dict) -> dict:
    gauges = site.get("usgs", [])
    if not gauges:
        return {"source": "USGS Water Services", "gauges": [], "notes": ["No gauged river for this site"]}
    ids = ",".join(g["id"] for g in gauges)
    data = get_json(f"{API}?format=json&sites={ids}&parameterCd=00060&period=P{RIVER_DAYS}D")
    by_id = {}
    for ts in data["value"]["timeSeries"]:
        sid = ts["sourceInfo"]["siteCode"][0]["value"]
        series = []
        for v in ts["values"][0]["value"]:
            t = parse_iso(v["dateTime"])
            q = num(v["value"])
            if t.minute == 0 and q is not None and q >= 0:  # hourly; negative = USGS no-data code
                series.append({"t": iso(t), "discharge_cms": r(q * CFS_TO_CMS, 2)})
        by_id[sid] = series
    out = []
    for g in gauges:
        series = by_id.get(g["id"], [])
        out.append({**g, "series": series, "latest": series[-1] if series else None,
                    "url": f"https://waterdata.usgs.gov/monitoring-location/{g['id']}/"})
    return {"source": "USGS Water Services (provisional data)", "gauges": out, "notes": [],
            "units": {"discharge_cms": "m³/s"}}
