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


def _finish(site: dict, meta: dict, provider: str, url: str, rows: dict[str, dict]) -> dict:
    series = [rows[t] for t in sorted(rows) if any(rows[t].get(k) is not None for k in KEYS)]
    st = {"id": meta["id"], "name": meta["name"], "provider": provider, "url": url,
          "lat": meta.get("lat"), "lon": meta.get("lon"), "series": series,
          "variables": [k for k in KEYS if any(row.get(k) is not None for row in series)]}
    if st["lat"] is not None:
        st["distance_km"] = round(distance_km(site["lat"], site["lon"], st["lat"], st["lon"]), 1)
    if not series:
        st["status"] = "no data"
    else:
        age = utcnow() - parse_iso(series[-1]["t"])
        st["status"] = "stale" if age > timedelta(days=MAX_AGE_DAYS) else "ok"
        st["latest"] = {k: next((row[k] for row in reversed(series) if row.get(k) is not None), None)
                        for k in KEYS}
        st["latest"]["t"] = series[-1]["t"]
    return st


def _coops(site: dict, s: dict) -> dict:
    rows: dict[str, dict] = {}
    errors = []
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
            rows.setdefault(iso(t), {"t": iso(t)})[key] = r(num(d.get(field)))
    st = _finish(site, s, "NOAA CO-OPS",
                 f"https://tidesandcurrents.noaa.gov/stationhome.html?id={s['id']}", rows)
    if errors:
        st["notes"] = errors
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
    pick = {key: next((cols[c] for c in names if c in cols), None) for key, names in ERDDAP_VARS.items()}
    meta = dict(s)
    rows: dict[str, dict] = {}
    for row in table["rows"]:
        t = parse_iso(row[cols["time"]])
        t = t.replace(minute=t.minute - t.minute % 30, second=0)
        rec = rows.setdefault(iso(t), {"t": iso(t)})
        for key, i in pick.items():
            v = num(row[i]) if i is not None else None
            if v is not None:
                rec[key] = r(v)
        if meta.get("lat") is None and "latitude" in cols and num(row[cols["latitude"]]) is not None:
            meta["lat"], meta["lon"] = num(row[cols["latitude"]]), num(row[cols["longitude"]])
    return _finish(site, meta, "IOOS Sensors ERDDAP",
                   f"https://erddap.sensors.ioos.us/erddap/tabledap/{s['id']}.html", rows)


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
