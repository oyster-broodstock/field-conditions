"""National Weather Service: hourly gridded forecast and nearby surface observations.

The forecast grid cell and observation stations are looked up from the site's
coordinates (api.weather.gov/points), so nothing per-site is hard-coded.
"""
from __future__ import annotations

from config import OBS_HOURS
from sources.common import (distance_km, get_json, hour_floor, iso, parse_iso, parse_valid_time, r,
                            timedelta, utcnow)

BASE = "https://api.weather.gov"
GEO = "application/geo+json"
KMH_TO_MS = 1 / 3.6

GRID_FIELDS = {  # gridpoint property -> (output key, converter, split over duration)
    "temperature": ("air_temp_c", lambda v: r(v, 1), False),
    "windSpeed": ("wind_ms", lambda v: r(v * KMH_TO_MS, 1), False),
    "windGust": ("gust_ms", lambda v: r(v * KMH_TO_MS, 1), False),
    "skyCover": ("sky_pct", lambda v: v, False),
    "quantitativePrecipitation": ("qpf_mm", lambda v: r(v, 2), True),
}


def _point(site: dict) -> dict:
    return get_json(f"{BASE}/points/{site['lat']},{site['lon']}", accept=GEO)["properties"]


def forecast(site: dict) -> dict:
    grid_url = _point(site)["forecastGridData"]
    props = get_json(grid_url, accept=GEO)["properties"]
    start = hour_floor(utcnow())
    end = start + timedelta(days=7)
    hours: dict[str, dict] = {}
    for prop, (key, conv, split) in GRID_FIELDS.items():
        for item in props.get(prop, {}).get("values", []):
            t0, n = parse_valid_time(item["validTime"])
            value = item["value"]
            if value is not None and split:
                value = value / n
            for h in range(n):
                t = t0 + timedelta(hours=h)
                if start <= t < end:
                    hours.setdefault(iso(t), {"t": iso(t)})[key] = None if value is None else conv(value)
    return {"source": "NWS gridpoint forecast", "grid": grid_url.rsplit("/gridpoints/", 1)[-1],
            "source_url": f"https://forecast.weather.gov/MapClick.php?lat={site['lat']}&lon={site['lon']}",
            "updated": props.get("updateTime"), "hourly": [hours[k] for k in sorted(hours)],
            "units": {"air_temp_c": "°C", "wind_ms": "m/s", "gust_ms": "m/s", "qpf_mm": "mm/h", "sky_pct": "%"}}


def _val(props, key, conv=lambda v: v):
    v = (props.get(key) or {}).get("value")
    return None if v is None else conv(v)


def observations(site: dict, max_stations: int = 2) -> dict:
    feats = get_json(_point(site)["observationStations"], accept=GEO)["features"]
    stations = []
    for f in feats[:25]:
        lon, lat = f["geometry"]["coordinates"][:2]
        stations.append({"id": f["properties"]["stationIdentifier"], "name": f["properties"]["name"].strip(),
                         "lat": lat, "lon": lon,
                         "distance_km": round(distance_km(site["lat"], site["lon"], lat, lon), 1)})
    stations.sort(key=lambda s: s["distance_km"])
    start = iso(utcnow() - timedelta(hours=OBS_HOURS))
    out = []
    for st in stations:
        if len(out) >= max_stations:
            break
        try:
            obs = get_json(f"{BASE}/stations/{st['id']}/observations?start={start}", accept=GEO)["features"]
        except Exception:
            continue
        hourly: dict[str, dict] = {}
        for o in obs:
            p = o["properties"]
            t = iso(hour_floor(parse_iso(p["timestamp"])))
            rec = hourly.setdefault(t, {"t": t})
            for key, val in (("air_temp_c", _val(p, "temperature", lambda v: r(v, 1))),
                             ("wind_ms", _val(p, "windSpeed", lambda v: r(v * KMH_TO_MS, 1))),
                             ("gust_ms", _val(p, "windGust", lambda v: r(v * KMH_TO_MS, 1))),
                             ("rh_pct", _val(p, "relativeHumidity", lambda v: round(v)))):
                if val is not None and rec.get(key) is None:  # features arrive newest first
                    rec[key] = val
        series = [hourly[k] for k in sorted(hourly)]
        if sum(x.get("air_temp_c") is not None for x in series) < max(len(series) / 2, 1):
            continue  # skip stations that rarely report temperature
        out.append({**st, "series": series, "latest": series[-1],
                    "url": f"https://www.weather.gov/wrh/timeseries?site={st['id']}"})
    if not out:
        raise RuntimeError("no nearby station reported air temperature")
    return {"source": "NWS / MADIS surface observations", "stations": out,
            "units": {"air_temp_c": "°C", "wind_ms": "m/s", "gust_ms": "m/s", "rh_pct": "%"}}
