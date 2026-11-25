"""Offline tests: python3 -m unittest discover ingest/tests"""
import concurrent.futures
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8
    ZoneInfo = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "baseline"))

import fake_api  # noqa: E402

fake_api.install()

import archive  # noqa: E402
import fetch  # noqa: E402
import health  # noqa: E402
import history  # noqa: E402
import loggers  # noqa: E402
from config import load_sites  # noqa: E402
from sources import common, nws, rain, water  # noqa: E402


class Sites(unittest.TestCase):
    def test_config(self):
        sites = load_sites()
        self.assertEqual(len({s["id"] for s in sites}), len(sites))
        self.assertEqual(sum(s["kind"] == "field" for s in sites), 7)
        for s in sites:
            for k in ("name", "coast", "node", "lat", "lon", "tz", "tide", "kind"):
                self.assertIn(k, s, s["id"])
            self.assertIn(s["kind"], ("field", "hatchery"), s["id"])
            self.assertIn(s["coast"], ("Atlantic", "Gulf", "Pacific"), s["id"])
            self.assertTrue(-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180, s["id"])
            if ZoneInfo is not None:
                ZoneInfo(s["tz"])
            self.assertTrue(s["tide"].get("id") and s["tide"].get("name"), s["id"])
            self.assertTrue(s.get("coops") or s.get("erddap"), f"{s['id']} has no water station")
            for st in s.get("coops", []) + s.get("erddap", []):
                if st.get("lat") is not None or st.get("lon") is not None:
                    self.assertTrue(-90 <= st["lat"] <= 90 and -180 <= st["lon"] <= 180, st["id"])
            if "baseline" in s:
                self.assertIn(s["baseline"].get("provider"), ("coops", "erddap"), s["id"])
                self.assertTrue(s["baseline"].get("id"), s["id"])


class Ingest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {s["id"]: fetch.fetch_site(s, None) for s in load_sites()}

    def test_every_source_ok(self):
        for sid, (doc, status) in self.docs.items():
            for name in fetch.SOURCES:
                self.assertTrue(status[name]["ok"], f"{sid}/{name}: {status[name]}")
                self.assertIn(name, doc)

    def test_water(self):
        doc, _ = self.docs["york"]
        st = doc["water"]["stations"][0]
        self.assertEqual(st["status"], "ok")
        self.assertEqual(st["variables"], ["water_temp_c", "salinity_psu"])
        self.assertAlmostEqual(st["distance_km"], 3.0, delta=0.5)
        self.assertEqual(len(st["series"]), 336)  # 7 days at 30 minutes
        # ERDDAP dataset that names its temperature column differently, and takes lat/lon from the data
        cbi = next(s for s in self.docs["corpus"][0]["water"]["stations"] if s["id"] == "ism-gcoos-cbi_074")
        self.assertEqual(cbi["variables"], ["water_temp_c", "salinity_psu"])  # do_mgl is skipped in sites.json
        ilm2 = next(s for s in self.docs["topsail"][0]["water"]["stations"] if s["id"] == "org_cormp_ilm2")
        self.assertIn("do_mgl", ilm2["variables"])

    def test_implausible_values_are_dropped(self):
        buoy = next(s for s in self.docs["hungars"][0]["water"]["stations"] if "44058" in s["id"])
        self.assertEqual(buoy["variables"], ["water_temp_c", "do_mgl"])
        self.assertIn("salinity_psu values outside the plausible range", buoy["notes"][0])

    def test_water_gaps_are_reported(self):
        site = {"lat": 0, "lon": 0, "coops": [{"id": "0000000", "name": "Dead", "lat": 0, "lon": 0.1,
                                               "products": ["water_temperature"]}],
                "erddap": [{"id": "nodata", "name": "Empty"}]}
        out = water.fetch(site)
        self.assertEqual([s["status"] for s in out["stations"]], ["no data", "no data"])

    def test_tides_rivers_weather_rain(self):
        doc, _ = self.docs["willapa"]
        self.assertGreater(len(doc["tides"]["curve"]), 200)
        self.assertEqual(len(doc["rivers"]["gauges"]), 2)
        self.assertTrue(all(x["discharge_cms"] > 0 for x in doc["rivers"]["gauges"][0]["series"]))
        self.assertEqual(self.docs["york"][0]["observations"]["stations"][0]["id"], "KAAA")  # nearest first
        self.assertEqual(doc["forecast"]["hourly"][0]["wind_ms"], 5.0)
        self.assertEqual(doc["forecast"]["hourly"][0]["qpf_mm"], 1.0)  # 6 mm over 6 h
        self.assertIsNotNone(doc["rain"]["totals_mm"]["h168"])
        self.assertEqual(self.docs["hungars"][0]["rivers"]["gauges"], [])

    def test_failure_keeps_previous(self):
        site = dict(load_sites()[0], usgs=[{"id": "bad", "name": "x"}])
        prev = {"rivers": {"gauges": [], "fetched_at": "2026-01-01T00:00:00Z"}}
        doc, status = fetch.fetch_site(site, prev, only=["rivers"])
        self.assertFalse(status["rivers"]["ok"])
        self.assertTrue(status["rivers"]["using_previous"])
        self.assertEqual(doc["rivers"]["fetched_at"], "2026-01-01T00:00:00Z")

    def test_summary(self):
        s = fetch.summarize(self.docs["york"][0])
        self.assertIn("v", s["water_temp_c"])
        self.assertEqual(len(s["water_temp_c"]["series"]), 168)
        self.assertIn("salinity_psu", s)
        self.assertNotIn("tide", s)

    def test_archive_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, dest = Path(tmp) / "data", Path(tmp) / "archive"
            data.mkdir()
            (data / "york.json").write_text(json.dumps(self.docs["york"][0]))
            (data / "meta.json").write_text("{}")
            first = archive.archive(data, dest)
            self.assertGreater(first, 500)
            self.assertEqual(archive.archive(data, dest), 0)
            files = list((dest / "york").glob("*.csv"))
            self.assertTrue(files)
            lines = files[0].read_text().splitlines()
            self.assertEqual(lines[0], ",".join(archive.HEADER))
            self.assertNotIn("qpf_mm", files[0].read_text())  # forecasts are not archived


class Baseline(unittest.TestCase):
    def test_summarize(self):
        hourly = []
        for day in range(1, 29):
            for h in range(24):
                hourly.append((f"2024-07-{day:02d}T{h:02d}:00", 24 + (h == 15) * (8 if day == 10 else 2)))
                hourly.append((f"2024-01-{day:02d}T{h:02d}:00", 5.0))
        hourly.append(("2024-07-11T00:00", 99.0))  # implausible, dropped
        out = history.summarize(hourly, [2023, 2024])
        self.assertEqual(out["annual"][0], {"year": 2023, "coverage": 0})
        y = out["annual"][1]
        self.assertEqual((y["max_hourly"], y["max_date"]), (32.0, "2024-07-10"))
        self.assertEqual(y["days_ge"]["25"], 28)
        self.assertEqual(y["days_ge"]["30"], 1)
        self.assertEqual(out["monthly"][0]["mean"], 5.0)
        self.assertEqual(out["monthly"][6]["max_hourly"], 32.0)
        self.assertIsNone(out["monthly"][3]["mean"])

    def test_max_7day_mean_requires_consecutive_days(self):
        # 7 days with a 2-day gap in the middle should not form a 7-day rolling mean
        hourly = [
            (f"2024-07-{day:02d}T{h:02d}:00", 25.0)
            for day in (1, 2, 3, 6, 7, 8, 9)
            for h in range(24)
        ]
        out = history.summarize(hourly, [2024])
        self.assertIsNone(out["annual"][0]["max_7day_mean"])
        # 2024 is a leap year: 7 / 366 = 0.02
        self.assertEqual(out["annual"][0]["coverage"], round(7 / 366, 2))


class DataIntegrity(unittest.TestCase):
    def test_per_variable_latest_timestamp(self):
        now = fake_api.NOW
        old_t = common.iso(now - common.timedelta(days=2))
        new_t = common.iso(now - common.timedelta(minutes=30))
        rows = {
            old_t: {"t": old_t, "water_temp_c": 20.0, "salinity_psu": 18.5},
            new_t: {"t": new_t, "water_temp_c": 21.0},
        }
        st = water._finish(
            {"lat": 37.0, "lon": -76.0},
            {"id": "s1", "name": "Test", "lat": 37.0, "lon": -76.0},
            "NOAA CO-OPS", "https://example.test", rows,
        )
        self.assertEqual(st["latest"]["t"], new_t)
        self.assertEqual(st["latest_t"]["water_temp_c"], new_t)
        self.assertEqual(st["latest_t"]["salinity_psu"], old_t)
        doc = {"site": {"id": "x", "name": "X"}, "water": {"stations": [st]}}
        s = fetch.summarize(doc)
        self.assertEqual(s["water_temp_c"]["t"], new_t)
        self.assertEqual(s["salinity_psu"]["t"], old_t)

    def test_erddap_preserves_exact_timestamps_and_summarizes_off_hour(self):
        now = fake_api.NOW.replace(minute=24, second=0, microsecond=0)
        t1 = common.iso(now - common.timedelta(hours=1))
        t2 = common.iso(now)
        orig = water.get_json
        try:
            water.get_json = lambda url, **kw: {
                "table": {
                    "columnNames": ["time", "latitude", "longitude", "sea_water_temperature"],
                    "rows": [[t1, 37.0, -76.0, 15.2], [t2, 37.0, -76.0, 15.8]],
                }
            }
            st = water._erddap({"lat": 37.0, "lon": -76.0}, {"id": "offhour", "name": "Off-hour"})
        finally:
            water.get_json = orig
        self.assertEqual([r["t"] for r in st["series"]], [t1, t2])
        s = fetch.summarize({"site": {"id": "x", "name": "X"}, "water": {"stations": [st]}})
        self.assertEqual(s["water_temp_c"]["series"], [[t1, 15.2], [t2, 15.8]])

    def test_nws_unit_conversion_and_duration_parsing(self):
        self.assertEqual(nws._convert(10.0, "wmoUnit:m_s-1", "speed", 1), 10.0)
        self.assertEqual(nws._convert(18.0, "wmoUnit:km_h-1", "speed", 1), 5.0)
        self.assertEqual(nws._convert(10.0, "wmoUnit:kn", "speed", 1), 5.1)
        self.assertEqual(nws._convert(68.0, "wmoUnit:degF", "temp", 1), 20.0)
        self.assertEqual(nws._convert(1.0, "wmoUnit:in", "precip", 1), 25.4)
        _, hrs = common.parse_valid_time("2026-09-24T18:00:00+00:00/PT1H30M0S")
        self.assertEqual(hrs, 2)
        with self.assertRaises(ValueError):
            common.parse_valid_time("2026-09-24T18:00:00+00:00/INVALID")

    def test_rain_stale_data_does_not_count_as_last_24h(self):
        old = common.utcnow() - common.timedelta(hours=40)
        old_day = old.date().isoformat()
        orig = rain.get_json
        try:
            rain.get_json = lambda url, **kw: (
                {"data": [{"end_valid": common.iso(old), "precip_in": 1.0}]}
                if f"valid={old_day}" in url else {"data": []}
            )
            out = rain.fetch({"lat": 37.0, "lon": -76.0})
        finally:
            rain.get_json = orig
        self.assertEqual(out["totals_mm"]["h24"], 0.0)
        self.assertEqual(out["totals_mm"]["h72"], 25.4)


class Reliability(unittest.TestCase):
    def test_get_json_retries_transient_and_deduplicates_concurrent(self):
        # Restore real get_json temporarily to test retry & thread-safe cache logic
        import importlib
        real_mod = importlib.reload(common)
        real_get_json = real_mod.get_json
        fake_api.install()  # re-install fake for other tests

        calls = {"n": 0}

        def fake_urlopen(req, timeout=40):
            calls["n"] += 1
            if "retry" in req.full_url and calls["n"] < 3:
                raise HTTPError(req.full_url, 503, "unavailable", {}, None)
            if "notfound" in req.full_url:
                raise HTTPError(req.full_url, 404, "not found", {}, None)
            return io.BytesIO(b'{"ok": true}')

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             mock.patch("time.sleep"):
            real_mod._cache.clear()
            self.assertEqual(real_get_json("https://example.test/retry", retries=3, backoff=0.01), {"ok": True})
            self.assertEqual(calls["n"], 3)

            calls["n"] = 0
            with self.assertRaises(HTTPError):
                real_get_json("https://example.test/notfound", retries=3, backoff=0.01)
            self.assertEqual(calls["n"], 1)  # 404 is not retried

            calls["n"] = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                res = list(pool.map(lambda _: real_get_json("https://example.test/shared"), range(4)))
            self.assertEqual(res, [{"ok": True}] * 4)
            self.assertEqual(calls["n"], 1)  # deduplicated across threads

    def test_health_check_flags_persistent_failures_and_stale_stations(self):
        now = common.parse_iso("2026-11-25T12:00:00Z")
        sites = [{"id": "york"}, {"id": "netarts"}]
        files = {
            "meta": {
                "generated_at": "2026-11-25T11:00:00Z",
                "sites": {
                    "york": {
                        "water": {"ok": False, "fetched_at": "2026-11-25T08:00:00Z", "error": "transient"},
                        "rain": {"ok": False, "fetched_at": "2026-11-22T00:00:00Z", "error": "timeout"},
                    },
                    "netarts": {"water": {"ok": True, "fetched_at": "2026-11-25T11:00:00Z"}},
                },
            },
            "york": {"water": {"stations": [{"id": "8637689", "name": "Yorktown", "status": "ok"}]}},
            "netarts": {
                "water": {
                    "stations": [
                        {"id": "9437540", "name": "Garibaldi", "status": "no data"},
                        {"id": "old1", "name": "Old Buoy", "status": "stale",
                         "latest": {"t": "2026-11-10T00:00:00Z"}},
                    ]
                }
            },
        }
        feed_issues, station_issues, gen = health.check_health(sites, files.get, now=now)
        self.assertEqual(gen, "2026-11-25T11:00:00Z")
        self.assertEqual(len(feed_issues), 1)
        self.assertIn("york / rain", feed_issues[0])
        self.assertEqual(len(station_issues), 2)
        report = health.format_report(feed_issues, station_issues, gen)
        self.assertIn("Garibaldi", report)
        self.assertIn("Old Buoy", report)


class ProjectLoggers(unittest.TestCase):
    def test_manchester_hobo_xlsx(self):
        xlsx = Path(__file__).resolve().parent.parent.parent / "loggers" / "manchester" / "hobo_22105353_2026-08_2026-11.xlsx"
        parsed = loggers.parse_logger_file(xlsx, "America/Los_Angeles")
        self.assertEqual(parsed["dropped"], 0)
        self.assertEqual(parsed["skipped_blank_ts"], 6)
        self.assertEqual(parsed["details"]["product"], "MX2203")
        self.assertEqual(parsed["details"]["serial"], "22105353")
        summary = loggers.summarize_deployment(
            "manchester", "manchester/hobo_22105353_2026-08_2026-11.xlsx", parsed, "America/Los_Angeles"
        )
        self.assertEqual(summary["n_samples"], 13679)
        self.assertEqual(summary["interval_min"], 10.0)
        self.assertEqual(summary["start_utc"], "2026-08-14T21:00:00Z")  # 14:00 PDT
        self.assertEqual(summary["end_utc"], "2026-11-17T21:40:00Z")    # 13:40 PST
        wt = summary["variables"]["water_temp_c"]
        self.assertEqual(wt["stats"]["min"], 11.14)
        self.assertEqual(wt["stats"]["max"], 21.38)
        self.assertEqual(wt["stats"]["max_date"], "2026-08-31")
        self.assertEqual(len(wt["daily"]), 96)

    def test_hoboconnect_csv_and_generic_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            hobo_csv = Path(tmp) / "hobo.csv"
            hobo_csv.write_text(
                '#,Date-Time (PDT/PST),"Temperature , °C"\n'
                '1,2026-08-14 14:00:00,14.5\n'
                '2,2026-08-14 14:10:00,14.7\n'
                ',,14.7\n'
                '#,Date-Time (PDT/PST),Host Connected\n'
                '1,2026-08-14 13:22:00,Logged\n'
                'Details,,,\n'
                ',,Product,MX2203\n'
                ',,Serial Number,999\n'
            )
            p = loggers.parse_logger_file(hobo_csv, "America/Los_Angeles")
            self.assertEqual(len(p["records"]), 2)
            self.assertEqual(p["details"]["product"], "MX2203")
            self.assertEqual(p["details"]["serial"], "999")

            gen_csv = Path(tmp) / "generic.csv"
            gen_csv.write_text(
                "datetime_utc,temp_f,salinity_psu\n"
                "2026-09-01T12:00:00Z,68.0,28.5\n"
                "2026-09-01T13:00:00Z,212.0,29.0\n"  # 100 C -> implausible, dropped
            )
            g = loggers.parse_logger_file(gen_csv, "America/New_York")
            self.assertEqual(g["dropped"], 1)
            temps = [v for _, var, v in g["records"] if var == "water_temp_c"]
            sals = [v for _, var, v in g["records"] if var == "salinity_psu"]
            self.assertEqual(temps, [20.0])
            self.assertEqual(sals, [28.5, 29.0])

    def test_logger_ingest_and_archive_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ldir, out, arch = root / "loggers", root / "web_loggers", root / "archive"
            (ldir / "manchester").mkdir(parents=True)
            (ldir / "manchester" / "cage.csv").write_text(
                "datetime_utc,water_temp_c\n2026-08-15T00:00:00Z,14.2\n2026-08-15T00:10:00Z,14.4\n"
            )
            counts = loggers.ingest_all(ldir, out, archive_dir=arch)
            self.assertEqual(counts, {"manchester": 1})
            doc = json.loads((out / "manchester.json").read_text())
            self.assertEqual(doc["deployments"][0]["n_samples"], 2)

            csv_path = arch / "manchester" / "2026.csv"
            lines = csv_path.read_text().splitlines()
            self.assertEqual(lines[0], ",".join(archive.HEADER))
            self.assertEqual(len(lines), 3)
            self.assertIn(",project_logger,cage,water_temp_c,", lines[1])

            # Re-running does not duplicate archive rows
            loggers.ingest_all(ldir, out, archive_dir=arch)
            self.assertEqual(len(csv_path.read_text().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
