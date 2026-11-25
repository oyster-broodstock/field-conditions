"""Historical water temperature baseline per site (run by hand or from baseline.yml, not hourly).

Usage:
    python3 baseline/history.py [--start 2016] [--end 2025] [--only york willapa]

For each site, downloads hourly water temperature from the station named in its "baseline"
entry in web/sites.json (NOAA CO-OPS, or an IOOS ERDDAP dataset averaged to the hour) and
writes web/baseline/<site_id>.json with:

    monthly   climatology of daily means by calendar month (mean, p05, p95), plus the
              highest hourly value seen in that month
    annual    per year: hourly maximum and its date, 99th percentile, warmest 7-day mean,
              days whose daily maximum reached each threshold, and data coverage

The station is usually not in the site's own water body; its distance is in the output.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))

from config import APP, ROOT, load_sites  # noqa: E402
from sources.common import get_json, iso, num, utcnow  # noqa: E402

THRESHOLDS_C = [20, 25, 28, 30, 32, 34]
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
ERDDAP = "https://erddap.sensors.ioos.us/erddap/tabledap"


def coops_year(station: str, year: int) -> list[tuple[str, float]]:
    url = (f"{COOPS}?product=water_temperature&station={station}&begin_date={year}0101"
           f"&end_date={year}1231&interval=h&time_zone=gmt&units=metric&format=json&application={APP}")
    data = get_json(url, timeout=120)
    if "error" in data:
        return []
    return [(d["t"].replace(" ", "T"), num(d["v"])) for d in data.get("data", []) if num(d["v"]) is not None]


def erddap_year(dataset: str, year: int) -> list[tuple[str, float]]:
    url = (f"{ERDDAP}/{dataset}.json?time,sea_water_temperature&time%3E={year}-01-01"
           f"&time%3C{year + 1}-01-01&orderByMean(%22time/1hour%22)")
    try:
        rows = get_json(url, timeout=180)["table"]["rows"]
    except Exception:
        return []
    return [(t[:16], num(v)) for t, v in rows if num(v) is not None]


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def summarize(hourly: list[tuple[str, float]], years: list[int]) -> dict:
    """hourly: (YYYY-MM-DDTHH:MM, degC). Plausibility filter: -2 to 40 degC."""
    hourly = [(t, v) for t, v in hourly if -2 <= v <= 40]
    days = defaultdict(list)
    for t, v in hourly:
        days[t[:10]].append(v)
    daily = {d: (sum(v) / len(v), max(v)) for d, v in days.items() if len(v) >= 12}

    monthly = []
    for m in range(1, 13):
        means = sorted(mean for d, (mean, _) in daily.items() if int(d[5:7]) == m)
        hours = [v for t, v in hourly if int(t[5:7]) == m]
        monthly.append({"month": m, "n_days": len(means),
                        "mean": r1(sum(means) / len(means)) if means else None,
                        "p05": r1(pct(means, 0.05)), "p95": r1(pct(means, 0.95)),
                        "max_hourly": r1(max(hours)) if hours else None})

    annual = []
    for y in years:
        hrs = [(t, v) for t, v in hourly if t.startswith(str(y))]
        dly = sorted((d, mm) for d, mm in daily.items() if d.startswith(str(y)))
        if not hrs:
            annual.append({"year": y, "coverage": 0})
            continue
        tmax, vmax = max(hrs, key=lambda x: x[1])
        week = [sum(m for _, (m, _) in dly[i:i + 7]) / 7 for i in range(max(len(dly) - 6, 0))]
        annual.append({"year": y, "coverage": round(len(dly) / 365, 2),
                       "max_hourly": r1(vmax), "max_date": tmax[:10],
                       "p99_hourly": r1(pct(sorted(v for _, v in hrs), 0.99)),
                       "max_7day_mean": r1(max(week)) if week else None,
                       "days_ge": {str(th): sum(mx >= th for _, (_, mx) in dly) for th in THRESHOLDS_C}})
    return {"monthly": monthly, "annual": annual}


def r1(v):
    return None if v is None else round(v, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2016)
    ap.add_argument("--end", type=int, default=utcnow().year - 1)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    years = list(range(args.start, args.end + 1))
    out = ROOT / "web" / "baseline"
    out.mkdir(parents=True, exist_ok=True)
    cache: dict[tuple, dict] = {}
    for site in load_sites():
        b = site.get("baseline")
        if not b or (args.only and site["id"] not in args.only):
            continue
        key = (b["provider"], b["id"])
        if key not in cache:
            fn = coops_year if b["provider"] == "coops" else erddap_year
            hourly = [row for y in years for row in fn(b["id"], y)]
            print(f"{b['provider']}:{b['id']}  {len(hourly)} hourly values")
            cache[key] = summarize(hourly, years)
        name = next((s["name"] for s in site.get("coops", []) + site.get("erddap", []) if s["id"] == b["id"]), b["id"])
        doc = {"site_id": site["id"], "variable": "water_temp_c", "units": "°C",
               "station": {"provider": b["provider"], "id": b["id"], "name": name},
               "years": [years[0], years[-1]], "thresholds_c": THRESHOLDS_C,
               "generated_at": iso(utcnow()), **cache[key]}
        (out / f"{site['id']}.json").write_text(json.dumps(doc, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
