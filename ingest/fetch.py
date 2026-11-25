"""Fetch public environmental data for every site and write JSON for the static site.

Usage:
    python3 ingest/fetch.py [--out web/data] [--fallback-url https://.../data] [--only-sites york ...]

Output:
    web/data/<site_id>.json   every source for one site
    web/data/summary.json     latest values and a 7-day water temperature series per site
    web/data/meta.json        per-site, per-source status (drives the freshness table)

Each source is fetched independently; one failing source never blocks the others. If a
source fails and --fallback-url is given, the previously published section is reused so the
site keeps showing the last good data (its age is visible in meta.json and on the page).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_sites  # noqa: E402
from sources import nws, rain, rivers, tides, water  # noqa: E402
from sources.common import iso, utcnow  # noqa: E402

SOURCES = {
    "tides": tides.fetch,
    "water": water.fetch,
    "rivers": rivers.fetch,
    "observations": nws.observations,
    "forecast": nws.forecast,
    "rain": rain.fetch,
}
SITE_FIELDS = ("id", "name", "kind", "coast", "node", "species", "lat", "lon", "tz", "context", "gaps")


def load_previous(out: Path, fallback_url: str | None, name: str):
    p = out / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    if fallback_url:
        try:
            with urllib.request.urlopen(f"{fallback_url.rstrip('/')}/{name}.json", timeout=20) as resp:
                return json.load(resp)
        except Exception:
            return None
    return None


def fetch_site(site: dict, previous: dict | None, only: list[str] | None = None) -> tuple[dict, dict]:
    doc = {"site": {k: site.get(k) for k in SITE_FIELDS}}
    status = {}
    for name, fn in SOURCES.items():
        prev_section = (previous or {}).get(name)
        if only and name not in only:
            if prev_section is not None:
                doc[name] = prev_section
            continue
        t0 = time.time()
        try:
            data = fn(site)
            data["fetched_at"] = iso(utcnow())
            doc[name] = data
            status[name] = {"ok": True, "fetched_at": data["fetched_at"]}
            print(f"[ok]   {site['id']:16s} {name:13s} {time.time() - t0:5.1f}s")
        except Exception as e:
            traceback.print_exc()
            status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300],
                            "attempted_at": iso(utcnow()),
                            "fetched_at": (prev_section or {}).get("fetched_at")}
            if prev_section is not None:
                doc[name] = prev_section
                status[name]["using_previous"] = True
            print(f"[FAIL] {site['id']:16s} {name:13s} {e}")
    return doc, status


def summarize(doc: dict) -> dict:
    """Headline values for the map and the comparison page."""
    s = dict(doc["site"])
    stations = [st for st in (doc.get("water") or {}).get("stations", []) if st.get("status") == "ok"]
    for key in ("water_temp_c", "salinity_psu", "do_mgl", "ph"):
        st = next((x for x in stations if x["latest"].get(key) is not None), None)
        if st:
            s[key] = {"v": st["latest"][key], "t": st.get("latest_t", {}).get(key, st["latest"]["t"]),
                      "station": st["name"], "distance_km": st.get("distance_km")}
            if key in ("water_temp_c", "salinity_psu"):  # hourly series for the comparison chart
                by_hour = {}
                for row in st["series"]:
                    if row.get(key) is not None:
                        hr = row["t"][:13]
                        if hr not in by_hour or row["t"][14:16] == "00":
                            by_hour[hr] = [row["t"], row[key]]
                s[key]["series"] = [by_hour[hr] for hr in sorted(by_hour)]
    obs = (doc.get("observations") or {}).get("stations", [])
    if obs and obs[0]["latest"].get("air_temp_c") is not None:
        s["air_temp_c"] = {"v": obs[0]["latest"]["air_temp_c"], "t": obs[0]["latest"]["t"],
                           "station": obs[0]["name"], "distance_km": obs[0]["distance_km"]}
    rain_totals = (doc.get("rain") or {}).get("totals_mm")
    if rain_totals:
        s["rain_72h_mm"] = rain_totals.get("h72")
    gauges = [g for g in (doc.get("rivers") or {}).get("gauges", []) if g.get("latest")]
    if gauges:
        s["discharge_cms"] = {"v": gauges[0]["latest"]["discharge_cms"], "station": gauges[0]["name"]}
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "web" / "data"))
    ap.add_argument("--fallback-url", default=None)
    ap.add_argument("--only", nargs="*", help="fetch only these sources")
    ap.add_argument("--only-sites", nargs="*", help="fetch only these site ids")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = load_previous(out, args.fallback_url, "meta") or {}
    statuses = meta.get("sites", {})
    summaries = {s["id"]: s for s in (load_previous(out, args.fallback_url, "summary") or {}).get("sites", [])}

    sites = load_sites()
    for site in sites:
        if args.only_sites and site["id"] not in args.only_sites:
            continue
        previous = load_previous(out, args.fallback_url, site["id"])
        doc, status = fetch_site(site, previous, args.only)
        doc["generated_at"] = iso(utcnow())
        (out / f"{site['id']}.json").write_text(json.dumps(doc, separators=(",", ":")))
        statuses[site["id"]] = {**statuses.get(site["id"], {}), **status}
        summaries[site["id"]] = summarize(doc)

    now = iso(utcnow())
    order = [s["id"] for s in sites]
    (out / "summary.json").write_text(json.dumps(
        {"generated_at": now, "sites": [summaries[i] for i in order if i in summaries]}, separators=(",", ":")))
    (out / "meta.json").write_text(json.dumps({"generated_at": now, "sites": statuses}, indent=1))
    ok = any(s.get("ok") for site in statuses.values() for s in site.values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
