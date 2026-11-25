"""Ingest historic project logger files (HOBOconnect .xlsx/.csv and generic .csv).

Reads raw logger files from loggers/<site_id>/*.{xlsx,csv}, merges optional metadata from
loggers/manifest.json, screens values against the same plausibility bounds as public water
stations, and writes:

1. Compact per-site web summaries in web/loggers/<site_id>.json (daily mean/min/max,
   monthly rollups, headline stats, and deployment metadata) for web/site.html.
2. Optional tidy archive rows in <archive_dir>/<site_id>/<year>.csv matching
   ingest/archive.py's exact 7-column schema (source="project_logger").

Usage:
    python3 ingest/loggers.py
    python3 ingest/loggers.py --archive-dir ../archive
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 fallback
    ZoneInfo = None

from ingest.archive import HEADER as ARCHIVE_HEADER, UNITS as ARCHIVE_UNITS
from ingest.config import load_sites
from ingest.sources.water import PLAUSIBLE

XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
EXCEL_EPOCH = datetime(1899, 12, 30)

DISPLAY_UNITS = {
    "water_temp_c": "°C",
    "salinity_psu": "PSU",
    "do_mgl": "mg/L",
    "ph": "",
}

# Standard US timezone offsets (standard, dst) used only if zoneinfo is unavailable (Python 3.8).
_US_TZ_FALLBACK = {
    "America/Los_Angeles": (-8, -7),
    "America/Denver": (-7, -6),
    "America/Chicago": (-6, -5),
    "America/New_York": (-5, -4),
    "America/Anchorage": (-9, -8),
    "Pacific/Honolulu": (-10, -10),
    "UTC": (0, 0),
}

_GMT_OFFSET_RE = re.compile(r"(?:GMT|UTC)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", re.I)
_INTERVAL_RE = re.compile(
    r"(?:(\d+)\s*hours?)?\s*(?:(\d+)\s*minutes?)?\s*(?:(\d+)\s*seconds?)?", re.I
)
_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %I:%M:%S %p",
    "%m/%d/%Y %I:%M:%S %p",
)


def _us_dst_active(dt: datetime) -> bool:
    """Approximate US DST rule (2nd Sunday in March 02:00 to 1st Sunday in Nov 02:00)."""
    y = dt.year
    # 2nd Sunday in March
    mar1 = datetime(y, 3, 1)
    dst_start = datetime(y, 3, 8 + (6 - mar1.weekday()) % 7, 2, 0)
    # 1st Sunday in November
    nov1 = datetime(y, 11, 1)
    dst_end = datetime(y, 11, 1 + (6 - nov1.weekday()) % 7, 2, 0)
    return dst_start <= dt < dst_end


def _localize_to_utc(
    dt: datetime, tz_name: str, fixed_offset: timezone | None = None, fold: int = 0
) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    if fixed_offset is not None:
        return dt.replace(tzinfo=fixed_offset).astimezone(timezone.utc)
    if tz_name in ("UTC", "Etc/UTC", "GMT"):
        return dt.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        return dt.replace(tzinfo=ZoneInfo(tz_name), fold=fold).astimezone(timezone.utc)
    std_h, dst_h = _US_TZ_FALLBACK.get(tz_name, (0, 0))
    offset_h = dst_h if (std_h != dst_h and _us_dst_active(dt) and fold == 0) else std_h
    return dt.replace(tzinfo=timezone(timedelta(hours=offset_h))).astimezone(timezone.utc)


def _header_tz_hint(col_name: str) -> timezone | None:
    """Return a fixed timezone if the timestamp column header explicitly names UTC or GMT±HH:MM."""
    low = col_name.lower()
    m = _GMT_OFFSET_RE.search(col_name)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hh = int(m.group(2))
        mm = int(m.group(3) or 0)
        return timezone(timedelta(minutes=sign * (hh * 60 + mm)))
    if "utc" in low:
        return timezone.utc
    return None


def _parse_timestamp(raw: str) -> datetime | None:
    s = raw.strip()
    if not s:
        return None
    # ISO 8601 with Z or ±HH:MM
    if s.endswith("Z"):
        try:
            return datetime.fromisoformat(s[:-1] + "+00:00")
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        if dt.year >= 1970:
            return dt
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _excel_serial_to_datetime(serial: float) -> datetime:
    dt = EXCEL_EPOCH + timedelta(days=serial)
    return (dt + timedelta(microseconds=500_000)).replace(microsecond=0)


def _col_index(cell_ref: str) -> int:
    col = 0
    for ch in cell_ref:
        if ch.isalpha():
            col = col * 26 + (ord(ch.upper()) - ord("A") + 1)
        else:
            break
    return col - 1


def _read_xlsx_sheets(path: Path) -> dict[str, list[list[str]]]:
    """Read all worksheets in an .xlsx file into {sheet_name: [[cell, ...], ...]}."""
    sheets: dict[str, list[list[str]]] = {}
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sroot.findall("m:si", XLSX_NS):
                shared.append("".join(t.text or "" for t in si.findall(".//m:t", XLSX_NS)))

        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels.findall("r:Relationship", REL_NS)
        }
        r_id_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for sheet_el in wb.findall(".//m:sheet", XLSX_NS):
            name = sheet_el.attrib["name"]
            rid = sheet_el.attrib.get(r_id_attr)
            target = rid_to_target.get(rid, "")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            if target not in zf.namelist():
                continue
            root = ET.fromstring(zf.read(target))
            rows: list[list[str]] = []
            for row_el in root.findall(".//m:sheetData/m:row", XLSX_NS):
                cells: dict[int, str] = {}
                for c in row_el.findall("m:c", XLSX_NS):
                    idx = _col_index(c.attrib.get("r", "A1"))
                    ctype = c.attrib.get("t")
                    if ctype == "inlineStr":
                        val = "".join(t.text or "" for t in c.findall(".//m:t", XLSX_NS))
                    else:
                        v = c.find("m:v", XLSX_NS)
                        val = v.text if (v is not None and v.text is not None) else ""
                        if ctype == "s" and val != "":
                            val = shared[int(val)]
                    cells[idx] = val
                if cells:
                    width = max(cells) + 1
                    rows.append([cells.get(i, "") for i in range(width)])
                else:
                    rows.append([])
            sheets[name] = rows
    return sheets


def _detect_columns(headers: list[str]) -> tuple[int | None, dict[int, tuple[str, bool]]]:
    """Identify timestamp column index and measurement columns {idx: (var_name, is_fahrenheit)}."""
    ts_idx: int | None = None
    var_cols: dict[int, tuple[str, bool]] = {}
    for i, raw in enumerate(headers):
        h = raw.strip().lower()
        if not h or h == "#":
            continue
        if ts_idx is None and any(
            k in h for k in ("date-time", "datetime", "date_time", "timestamp", "time")
        ):
            ts_idx = i
            continue
        if "temp" in h:
            is_f = ("°f" in h) or ("degf" in h) or h.endswith("_f") or "(f)" in h
            var_cols[i] = ("water_temp_c", is_f)
        elif "salin" in h or h in ("sal", "sal_psu", "salinity_psu"):
            var_cols[i] = ("salinity_psu", False)
        elif "dissolved oxygen" in h or h in ("do", "do_mgl", "do (mg/l)"):
            var_cols[i] = ("do_mgl", False)
        elif h == "ph" or h.startswith("ph ") or h.startswith("ph("):
            var_cols[i] = ("ph", False)
    return ts_idx, var_cols


def _extract_details(rows: list[list[str]]) -> dict[str, str]:
    """Pull key-value pairs from a HOBOconnect Details block or worksheet."""
    details: dict[str, str] = {}
    wanted = {
        "product": "product",
        "serial number": "serial",
        "manufacturer": "manufacturer",
        "logging interval": "logging_interval",
        "deployment number": "deployment_number",
    }
    for row in rows:
        non_empty = [c.strip() for c in row if c and c.strip()]
        if len(non_empty) >= 2:
            key = non_empty[0].lower()
            if key in wanted:
                details[wanted[key]] = non_empty[1]
    return details


def _parse_interval_min(text: str | None) -> float | None:
    if not text:
        return None
    m = _INTERVAL_RE.search(text)
    if not m or not any(m.groups()):
        return None
    hours = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(m.group(3) or 0)
    total = hours * 60 + mins + secs / 60.0
    return round(total, 2) if total > 0 else None


def parse_logger_file(path: Path, tz_name: str) -> dict:
    """Parse a HOBOconnect .xlsx/.csv or generic .csv into UTC-normalized readings & metadata."""
    ext = path.suffix.lower()
    details: dict[str, str] = {}
    excel_serial_dates = False

    if ext == ".xlsx":
        sheets = _read_xlsx_sheets(path)
        data_rows = sheets.get("Data") or next(iter(sheets.values()), [])
        if "Details" in sheets:
            details = _extract_details(sheets["Details"])
        excel_serial_dates = True
    elif ext == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            all_rows = list(csv.reader(fh))
        data_rows = []
        details_rows = []
        in_events = False
        in_details = False
        header_seen = False
        for row in all_rows:
            first = row[0].strip() if row else ""
            if first == "Details":
                in_details = True
                in_events = False
            if in_details:
                details_rows.append(row)
                continue
            if header_seen and first == "#":
                # Second '#' header starts the HOBOconnect Events table; skip until Details.
                in_events = True
                continue
            if in_events:
                continue
            if any(c.strip() for c in row):
                data_rows.append(row)
                header_seen = True
        if details_rows:
            details = _extract_details(details_rows)
    else:
        raise ValueError(f"Unsupported logger file extension: {path.suffix}")

    if not data_rows:
        raise ValueError(f"Empty logger file: {path}")

    headers = data_rows[0]
    ts_idx, var_cols = _detect_columns(headers)
    if ts_idx is None or not var_cols:
        raise ValueError(f"Could not detect timestamp and measurement columns in {path.name}: {headers}")

    fixed_offset = _header_tz_hint(headers[ts_idx])
    records: list[tuple[datetime, str, float]] = []
    seen_local: set[datetime] = set()
    dropped = 0
    skipped_blank_ts = 0

    for row in data_rows[1:]:
        if ts_idx >= len(row):
            skipped_blank_ts += 1
            continue
        raw_ts = row[ts_idx].strip()
        if not raw_ts:
            skipped_blank_ts += 1
            continue

        dt: datetime | None = None
        if excel_serial_dates:
            try:
                dt = _excel_serial_to_datetime(float(raw_ts))
            except ValueError:
                dt = _parse_timestamp(raw_ts)
        else:
            dt = _parse_timestamp(raw_ts)
        if dt is None:
            continue

        fold = 1 if (dt.tzinfo is None and dt in seen_local) else 0
        if dt.tzinfo is None:
            seen_local.add(dt)
        utc_dt = _localize_to_utc(dt, tz_name, fixed_offset=fixed_offset, fold=fold)

        for col_i, (var, is_f) in var_cols.items():
            if col_i >= len(row):
                continue
            raw_v = row[col_i].strip()
            if not raw_v:
                continue
            try:
                val = float(raw_v)
            except ValueError:
                continue
            if math.isnan(val) or math.isinf(val):
                continue
            if is_f:
                val = (val - 32.0) * 5.0 / 9.0
            lo, hi = PLAUSIBLE.get(var, (-1e9, 1e9))
            if lo <= val <= hi:
                records.append((utc_dt, var, val))
            else:
                dropped += 1

    records.sort(key=lambda r: (r[0], r[1]))
    return {
        "records": records,
        "details": details,
        "dropped": dropped,
        "skipped_blank_ts": skipped_blank_ts,
    }


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((len(s) - 1) * p))))
    return s[idx]


def _infer_interval_min(timestamps: list[datetime]) -> float | None:
    if len(timestamps) < 2:
        return None
    diffs = sorted(
        (b - a).total_seconds() / 60.0
        for a, b in zip(timestamps, timestamps[1:])
        if b > a
    )
    if not diffs:
        return None
    return round(diffs[len(diffs) // 2], 2)


def summarize_deployment(
    site_id: str,
    rel_file: str,
    parsed: dict,
    tz_name: str,
    meta: dict | None = None,
) -> dict:
    """Build a compact JSON-serializable summary for one logger deployment."""
    meta = meta or {}
    details = parsed["details"]
    records = parsed["records"]

    deploy_id = meta.get("station_id") or Path(rel_file).stem
    product = meta.get("product") or details.get("product")
    serial = meta.get("serial") or details.get("serial")
    default_label = (
        f"Project logger ({product} #{serial})"
        if product and serial
        else f"Project logger ({deploy_id})"
    )

    by_var: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    all_ts: list[datetime] = []
    for utc_dt, var, val in records:
        by_var[var].append((utc_dt, val))
        all_ts.append(utc_dt)

    unique_ts = sorted(set(all_ts))
    interval_min = _parse_interval_min(details.get("logging_interval")) or _infer_interval_min(unique_ts)

    variables_out: dict[str, dict] = {}
    for var, pts in by_var.items():
        vals = [v for _, v in pts]
        # Group by site-local date for daily and monthly summaries
        by_day: dict[str, list[float]] = defaultdict(list)
        max_val = -1e18
        max_date = ""
        for utc_dt, val in pts:
            if ZoneInfo is not None and tz_name not in ("UTC", "Etc/UTC", "GMT"):
                local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            else:
                std_h, dst_h = _US_TZ_FALLBACK.get(tz_name, (0, 0))
                approx = utc_dt + timedelta(hours=std_h)
                off = dst_h if (std_h != dst_h and _us_dst_active(approx.replace(tzinfo=None))) else std_h
                local_dt = utc_dt + timedelta(hours=off)
            day_key = local_dt.strftime("%Y-%m-%d")
            by_day[day_key].append(val)
            if val > max_val:
                max_val = val
                max_date = day_key

        daily = []
        by_month: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        for day_key in sorted(by_day):
            dv = by_day[day_key]
            d_mean = sum(dv) / len(dv)
            d_min = min(dv)
            d_max = max(dv)
            daily.append([day_key, round(d_mean, 2), round(d_min, 2), round(d_max, 2)])
            yr, mo = int(day_key[:4]), int(day_key[5:7])
            by_month[(yr, mo)].append((d_mean, d_max))

        monthly = []
        for (yr, mo) in sorted(by_month):
            d_means = [m for m, _ in by_month[(yr, mo)]]
            d_maxes = [mx for _, mx in by_month[(yr, mo)]]
            monthly.append({
                "year": yr,
                "month": mo,
                "n_days": len(d_means),
                "mean": round(sum(d_means) / len(d_means), 2),
                "p05": round(_pct(d_means, 0.05), 2),
                "p95": round(_pct(d_means, 0.95), 2),
                "max": round(max(d_maxes), 2),
            })

        variables_out[var] = {
            "unit": DISPLAY_UNITS.get(var, ""),
            "stats": {
                "min": round(min(vals), 2),
                "mean": round(sum(vals) / len(vals), 2),
                "p05": round(_pct(vals, 0.05), 2),
                "p95": round(_pct(vals, 0.95), 2),
                "p99": round(_pct(vals, 0.99), 2),
                "max": round(max(vals), 2),
                "max_date": max_date,
            },
            "daily": daily,
            "monthly": monthly,
        }

    return {
        "id": deploy_id,
        "file": rel_file,
        "label": meta.get("label") or default_label,
        "product": product,
        "serial": serial,
        "interval_min": interval_min,
        "start_utc": unique_ts[0].strftime("%Y-%m-%dT%H:%M:%SZ") if unique_ts else None,
        "end_utc": unique_ts[-1].strftime("%Y-%m-%dT%H:%M:%SZ") if unique_ts else None,
        "n_samples": len(unique_ts),
        "dropped": parsed["dropped"],
        "notes": meta.get("notes"),
        "variables": variables_out,
    }


def archive_logger_records(
    site_id: str, deploy_id: str, records: list[tuple[datetime, str, float]], dest: Path
) -> int:
    """Append tidy project-logger rows to dest/<site_id>/<year>.csv idempotently."""
    by_year: dict[str, list[list]] = defaultdict(list)
    for utc_dt, var, val in records:
        if var not in ARCHIVE_UNITS:
            continue
        ts = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        by_year[ts[:4]].append([
            ts, site_id, "project_logger", deploy_id, var, round(val, 3), ARCHIVE_UNITS[var]
        ])

    added = 0
    for year, rows in by_year.items():
        path = dest / site_id / f"{year}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        seen: set[tuple[str, str, str, str]] = set()
        if path.exists():
            with path.open(newline="") as fh:
                seen = {(x[0], x[2], x[3], x[4]) for x in csv.reader(fh) if len(x) >= 5}
        new = [x for x in rows if (x[0], x[2], x[3], x[4]) not in seen]
        if not new:
            continue
        write_header = not path.exists()
        with path.open("a", newline="") as fh:
            w = csv.writer(fh)
            if write_header:
                w.writerow(ARCHIVE_HEADER)
            w.writerows(sorted(new))
        added += len(new)
    return added


def ingest_all(
    loggers_dir: Path,
    out_dir: Path,
    archive_dir: Path | None = None,
    sites: list[dict] | None = None,
) -> dict[str, int]:
    """Ingest all logger files under loggers_dir/<site_id>/ and write web JSON summaries."""
    site_map = {s["id"]: s for s in (sites or load_sites())}
    manifest_path = loggers_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    if not loggers_dir.exists():
        return counts

    for site_dir in sorted(p for p in loggers_dir.iterdir() if p.is_dir()):
        site_id = site_dir.name
        if site_id not in site_map:
            print(f"Skipping unknown site directory: {site_id}", file=sys.stderr)
            continue
        site_tz = site_map[site_id]["tz"]
        files = sorted(
            f for f in site_dir.iterdir()
            if f.is_file() and f.suffix.lower() in (".xlsx", ".csv") and not f.name.startswith(".")
        )
        if not files:
            continue

        deployments = []
        for f in files:
            rel = f"{site_id}/{f.name}"
            meta = manifest.get(rel, {})
            tz_name = meta.get("tz") or site_tz
            parsed = parse_logger_file(f, tz_name)
            summary = summarize_deployment(site_id, rel, parsed, tz_name, meta=meta)
            deployments.append(summary)
            if archive_dir is not None:
                n = archive_logger_records(site_id, summary["id"], parsed["records"], archive_dir)
                print(f"  archived {n} rows from {rel}")

        deployments.sort(key=lambda d: d.get("start_utc") or "", reverse=True)
        doc = {
            "site_id": site_id,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deployments": deployments,
        }
        (out_dir / f"{site_id}.json").write_text(json.dumps(doc, indent=2) + "\n")
        counts[site_id] = len(deployments)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest historic project logger files.")
    ap.add_argument("--loggers-dir", type=Path, default=ROOT / "loggers")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "web" / "loggers")
    ap.add_argument("--archive-dir", type=Path, default=None,
                    help="Optional archive root to append tidy rows into <archive-dir>/<site_id>/<year>.csv")
    args = ap.parse_args()

    counts = ingest_all(args.loggers_dir, args.out_dir, archive_dir=args.archive_dir)
    if not counts:
        print("No logger files found.")
    else:
        for sid, n in counts.items():
            print(f"{sid}: {n} deployment(s) -> {args.out_dir / f'{sid}.json'}")


if __name__ == "__main__":
    main()
