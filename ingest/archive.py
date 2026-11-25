"""Append this run's observations to the permanent archive (one tidy CSV per site per year).

Usage:
    python3 ingest/archive.py web/data ../archive

The site only shows the last 7 days; the archive keeps every reading. Files are
archive/<site_id>/<year>.csv in long format:

    datetime_utc,site_id,source,station_id,variable,value,unit

Only observations are archived (water, river discharge, weather observations, Stage IV rain).
Forecasts and tide predictions are not, because they can be regenerated. Rows already in the
archive (same time, source, station and variable) are skipped, so the script can run every hour.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HEADER = ["datetime_utc", "site_id", "source", "station_id", "variable", "value", "unit"]
UNITS = {"water_temp_c": "degC", "salinity_psu": "PSU", "do_mgl": "mg/L", "ph": "pH",
         "discharge_cms": "m3/s", "air_temp_c": "degC", "wind_ms": "m/s", "gust_ms": "m/s",
         "rh_pct": "%", "precip_mm": "mm"}


def rows_for(doc: dict):
    sid = doc["site"]["id"]

    def emit(source, station, series):
        for rec in series or []:
            for var, val in rec.items():
                if var != "t" and val is not None and var in UNITS:
                    yield [rec["t"], sid, source, station, var, val, UNITS[var]]

    for st in (doc.get("water") or {}).get("stations", []):
        src = "coops" if st["provider"] == "NOAA CO-OPS" else "ioos_erddap"
        yield from emit(src, st["id"], st["series"])
    for g in (doc.get("rivers") or {}).get("gauges", []):
        yield from emit("usgs", g["id"], g["series"])
    for st in (doc.get("observations") or {}).get("stations", []):
        yield from emit("nws", st["id"], st["series"])
    yield from emit("stage4", "site", (doc.get("rain") or {}).get("hourly"))


def archive(data_dir: Path, dest: Path) -> int:
    added = 0
    for f in sorted(data_dir.glob("*.json")):
        if f.name in ("meta.json", "summary.json"):
            continue
        doc = json.loads(f.read_text())
        by_year = defaultdict(list)
        for row in rows_for(doc):
            by_year[row[0][:4]].append(row)
        for year, rows in by_year.items():
            path = dest / doc["site"]["id"] / f"{year}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            seen = set()
            if path.exists():
                with path.open(newline="") as fh:
                    seen = {(x[0], x[2], x[3], x[4]) for x in csv.reader(fh)}
            new = [x for x in rows if (x[0], x[2], x[3], x[4]) not in seen]
            if not new:
                continue
            write_header = not path.exists()
            with path.open("a", newline="") as fh:
                w = csv.writer(fh)
                if write_header:
                    w.writerow(HEADER)
                w.writerows(sorted(new))
            added += len(new)
    return added


if __name__ == "__main__":
    n = archive(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"archived {n} new rows")
