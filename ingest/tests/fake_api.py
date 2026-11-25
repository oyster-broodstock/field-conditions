"""Offline stand-in for the public APIs, shaped like the real responses (checked Nov 2026).

Used by the tests, and by `python3 ingest/tests/fake_api.py web/data` to fill the site with
synthetic data for local front-end work. Synthetic values are NOT real observations.
"""
from __future__ import annotations

import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _wave(i, base, amp, period):
    return round(base + amp * math.sin(2 * math.pi * i / period), 2)


def fake_get_json(url: str, timeout: int = 40, accept: str = "application/json"):
    seed = sum(map(ord, re.sub(r"\d{4}-\d\d-\d\d|\d{8}", "", url))) % 7
    if "datagetter" in url and "product=predictions" in url:
        t0 = NOW.replace(hour=0, minute=0) - timedelta(days=1)
        preds = [{"t": (t0 + timedelta(hours=6.2 * i)).strftime("%Y-%m-%d %H:%M"),
                  "v": str(round(0.2 + 1.6 * (i % 2) + 0.1 * seed, 3)), "type": "HL"[i % 2 == 0]}
                 for i in range(40)]
        return {"predictions": preds}
    if "datagetter" in url:
        if "station=0000000" in url:
            return {"error": {"message": "No data was found."}}
        field = "s" if "product=salinity" in url else "v"
        base, amp = (22 + seed, 3) if field == "s" else (12 + seed, 1.5)
        t0 = NOW.replace(minute=0) - timedelta(hours=168)
        return {"metadata": {"id": "x"},
                "data": [{"t": (t0 + timedelta(minutes=6 * i)).strftime("%Y-%m-%d %H:%M"),
                          field: str(_wave(i, base, amp, 124))} for i in range(1680)]}
    if "erddap" in url:
        if "nodata" in url:
            raise HTTPError(url, 404, "no rows", None, None)
        temp_col = "sea_surface_temperature" if "cbi_" in url else "sea_water_temperature"
        t0 = NOW - timedelta(hours=168)
        rows = [[(t0 + timedelta(minutes=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"), 34.1, -77.8,
                 _wave(i, 14 + seed, 1, 25), _wave(i, 30, 2, 50), None if i % 9 == 0 else 7.5]
                for i in range(336)]
        return {"table": {"columnNames": ["time", "latitude", "longitude", temp_col,
                                          "sea_water_practical_salinity",
                                          "mass_concentration_of_oxygen_in_sea_water"], "rows": rows}}
    if "waterservices.usgs.gov" in url:
        ids = re.search(r"sites=([\d,]+)", url).group(1).split(",")
        t0 = NOW.replace(minute=0) - timedelta(days=7)
        return {"value": {"timeSeries": [
            {"sourceInfo": {"siteCode": [{"value": sid}]},
             "values": [{"value": [{"value": str(200 + 10 * (i % 24) + int(sid[-2:])),
                                    "dateTime": (t0 + timedelta(minutes=15 * i)).isoformat()}
                                   for i in range(672)] + [{"value": "-999999", "dateTime": NOW.isoformat()}]}]}
            for sid in ids]}}
    if "/points/" in url:
        return {"properties": {"forecastGridData": "https://api.weather.gov/gridpoints/XXX/1,2",
                               "observationStations": "https://api.weather.gov/gridpoints/XXX/1,2/stations"}}
    if url.endswith("/gridpoints/XXX/1,2/stations"):
        return {"features": [{"geometry": {"coordinates": [-76.4, 37.2]},
                              "properties": {"stationIdentifier": "KAAA", "name": "Test Airport "}},
                             {"geometry": {"coordinates": [-76.9, 37.6]},
                              "properties": {"stationIdentifier": "KBBB", "name": "Far Airport"}}]}
    if url.endswith("/gridpoints/XXX/1,2"):
        t0 = NOW.replace(minute=0)
        vt = lambda i, d: f"{(t0 + timedelta(hours=i)).isoformat()}/PT{d}H"  # noqa: E731
        return {"properties": {"updateTime": NOW.isoformat(),
                               "temperature": {"values": [{"validTime": vt(i, 1), "value": _wave(i, 10, 4, 24)} for i in range(160)]},
                               "windSpeed": {"values": [{"validTime": vt(i * 3, 3), "value": 18.0} for i in range(50)]},
                               "windGust": {"values": [{"validTime": vt(i * 3, 3), "value": None} for i in range(50)]},
                               "skyCover": {"values": [{"validTime": vt(i * 6, 6), "value": 50} for i in range(28)]},
                               "quantitativePrecipitation": {"values": [{"validTime": vt(i * 6, 6), "value": 6.0 if i % 5 == 0 else 0} for i in range(28)]}}}
    if "/observations" in url:
        return {"features": [{"properties": {
            "timestamp": (NOW - timedelta(minutes=20 * i)).isoformat(),
            "temperature": {"value": _wave(i, 9, 3, 72)}, "windSpeed": {"value": 14.4},
            "windGust": {"value": None}, "relativeHumidity": {"value": 71.4}}} for i in range(200)]}
    if "stage4" in url:
        day = re.search(r"valid=([\d-]+)", url).group(1)
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        return {"data": [{"end_valid": (d0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "precip_in": 0.05 if (h + d0.day) % 11 == 0 else 0} for h in range(1, 25)]}
    raise AssertionError(f"unexpected URL in test: {url}")


def install():
    from sources import common, nws, rain, rivers, tides, water
    for mod in (common, nws, rain, rivers, tides, water):
        mod.get_json = fake_get_json


if __name__ == "__main__":
    install()
    import fetch
    sys.argv = ["fetch.py", "--out", sys.argv[1] if len(sys.argv) > 1 else "web/data"]
    import json
    print("Writing SYNTHETIC data (not real observations)")
    fetch.main()
    for name in ("meta", "summary"):  # the pages show a red banner when this flag is set
        p = Path(sys.argv[2]) / f"{name}.json"
        p.write_text(json.dumps({"synthetic": True, **json.loads(p.read_text())}))
