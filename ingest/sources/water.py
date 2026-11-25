"""Water temperature, salinity, dissolved oxygen and pH from public stations.

Two providers:
- NOAA CO-OPS data API (water_temperature, salinity), 6-minute data thinned to 30 minutes.
- IOOS Sensors ERDDAP (regional association, CBIBS, CORMP, TAMU-CC CBI and other platforms).
  Column names differ between datasets, so the whole recent table is requested and the
  first matching column for each variable is used.

Every station is reported with its distance from the site. A station with no recent data
is kept in the output with status "stale" or "no data", so gaps are visible on the page.
"""
from __future__ import annotations

from urllib.error import HTTPError

from config import APP, MAX_AGE_DAYS, WATER_HOURS
from sources.common import (datetime, distance_km, get_json, iso, num, parse_iso, r, timedelta,
                            timezone, utcnow)

COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
ERDDAP = "https://erddap.sensors.ioos.us/erddap/tabledap"

# output key -> ERDDAP column names, in order of preference
ERDDAP_VARS = {
    "water_temp_c": ["sea_water_temperature", "sea_surface_temperature"],
    "salinity_psu": ["sea_water_practical_salinity"],
    "do_mgl": ["mass_concentration_of_oxygen_in_sea_water",
               "mass_concentration_of_oxygen_in_sea_water_corrected"],
    "ph": ["sea_water_ph_reported_on_total_scale"],
}
KEYS = list(ERDDAP_VARS)
# Values outside these ranges are dropped and counted in the station's notes. Checked Nov 2026:
# some upstream feeds are mis-scaled (CBIBS 44058 salinity arrives 1000x too large).
PLAUSIBLE = {"water_temp_c": (-2, 40), "salinity_psu": (0, 42), "do_mgl": (0, 25), "ph": (6, 9.5)}


def _clean(key: str, v, dropped: dict):
    if v is None:
        return None
    lo, hi = PLAUSIBLE[key]
    if lo <= v <= hi:
        return r(v)
    dropped[key] = dropped.get(key, 0) + 1
    return None


def _drop_notes(dropped: dict) -> list[str]:
    return [f"{n} {k} values outside the plausible range were dropped" for k, n in dropped.items()]


def _finish(site: dict, meta: dict, provider: str, url: str, rows: dict[str, dict]) -> dict:
    series = [rows[t] for t in sorted(rows) if any(rows[t].get(k) is not None for k in KEYS)]
    st = {"id": meta["id"], "name": meta["name"], "provider": provider, "url": url,
          "lat": meta.get("lat"), "lon": meta.get("lon"), "series": series,
          "variables": [k for k in KEYS if any(row.get(k) is not None for row in series)]}
    if st["lat"] is not None and st["lon"] is not None:
        st["distance_km"] = round(distance_km(site["lat"], site["lon"], st["lat"], st["lon"]), 1)
    if not series:
        st["status"] = "no data"
    else:
        age = utcnow() - parse_iso(series[-1]["t"])
        st["status"] = "stale" if age > timedelta(days=MAX_AGE_DAYS) else "ok"
        latest, latest_t = {}, {}
        for k in KEYS:
            hit = next((row for row in reversed(series) if row.get(k) is not None), None)
            latest[k] = hit[k] if hit else None
            if hit:
                latest_t[k] = hit["t"]
        latest["t"] = series[-1]["t"]
        st["latest"] = latest
        st["latest_t"] = latest_t
    return st


def _coops(site: dict, s: dict) -> dict:
    rows: dict[str, dict] = {}
    errors, dropped = [], {}
    for product, key, field in (("water_temperature", "water_temp_c", "v"), ("salinity", "salinity_psu", "s")):
        if product not in s.get("products", []):
            continue
        url = (f"{COOPS}?product={product}&station={s['id']}&range={WATER_HOURS}&time_zone=gmt"
               f"&units=metric&format=json&application={APP}")
        data = get_json(url)
        if "error" in data:
            errors.append(f"{product}: {data['error'].get('message', '').strip()}")
            continue
        for d in data.get("data", []):
            t = datetime.strptime(d["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            if t.minute % 30:  # 6-minute data -> 30-minute
                continue
            rows.setdefault(iso(t), {"t": iso(t)})[key] = _clean(key, num(d.get(field)), dropped)
    st = _finish(site, s, "NOAA CO-OPS",
                 f"https://tidesandcurrents.noaa.gov/stationhome.html?id={s['id']}", rows)
    if errors or dropped:
        st["notes"] = errors + _drop_notes(dropped)
    return st


def _erddap(site: dict, s: dict) -> dict:
    url = f"{ERDDAP}/{s['id']}.json?&time%3E=now-{WATER_HOURS}hours"
    try:
        table = get_json(url, timeout=60)["table"]
    except HTTPError as e:
        if e.code != 404:  # ERDDAP answers 404 when no rows match the time range
            raise
        table = {"columnNames": [], "rows": []}
    cols = {name: i for i, name in enumerate(table["columnNames"])}
    pick = {key: next((cols[c] for c in names if c in cols), None)
            for key, names in ERDDAP_VARS.items() if key not in s.get("skip", [])}
    meta = {k: v for k, v in s.items() if k != "skip"}
    raw_rows: dict[str, dict] = {}
    dropped: dict[str, int] = {}
    for row in table["rows"]:
        ts = iso(parse_iso(row[cols["time"]]))
        rec = raw_rows.setdefault(ts, {"t": ts})
        for key, i in pick.items():
            v = _clean(key, num(row[i]), dropped) if i is not None else None
            if v is not None:
                rec[key] = v
        if (meta.get("lat") is None and "latitude" in cols and "longitude" in cols
                and num(row[cols["latitude"]]) is not None and num(row[cols["longitude"]]) is not None):
            meta["lat"], meta["lon"] = num(row[cols["latitude"]]), num(row[cols["longitude"]])
    # Thin to at most one observation per 30-minute bucket without mutating timestamps.
    rows: dict[str, dict] = {}
    seen_buckets: set[str] = set()
    for ts in sorted(raw_rows):
        rec = raw_rows[ts]
        if not any(rec.get(k) is not None for k in KEYS):
            continue
        t = parse_iso(ts)
        bucket = iso(t.replace(minute=t.minute - t.minute % 30, second=0, microsecond=0))
        if bucket not in seen_buckets:
            seen_buckets.add(bucket)
            rows[ts] = rec
    st = _finish(site, meta, "IOOS Sensors ERDDAP",
                 f"https://erddap.sensors.ioos.us/erddap/tabledap/{s['id']}.html", rows)
    if dropped:
        st["notes"] = _drop_notes(dropped)
    return st


def fetch(site: dict) -> dict:
    stations, notes = [], []
    for fn, group in ((_coops, site.get("coops", [])), (_erddap, site.get("erddap", []))):
        for s in group:
            try:
                stations.append(fn(site, s))
            except Exception as e:
                notes.append(f"{s['name']}: {type(e).__name__}: {e}")
    if not stations and notes:
        raise RuntimeError("; ".join(notes))
    stations.sort(key=lambda s: s.get("distance_km", 1e9))
    return {"source": "NOAA CO-OPS, IOOS Sensors ERDDAP", "stations": stations, "notes": notes,
            "units": {"water_temp_c": "°C", "salinity_psu": "PSU", "do_mgl": "mg/L", "ph": ""}}
