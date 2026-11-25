"""Engineering health check for published feeds and water stations.

Usage:
    python3 ingest/health.py --data-dir web/data
    python3 ingest/health.py --base-url https://.../data --out health.md

Flags feeds that have been failing longer than --max-fail-hours (default 48) and water
stations that are stale or have no data for longer than --max-stale-days (default 7).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_sites  # noqa: E402
from sources.common import get_json, parse_iso, timedelta, utcnow  # noqa: E402


def _load(name: str, data_dir: Path | None, base_url: str | None) -> dict | None:
    if data_dir is not None:
        p = data_dir / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None
    if base_url is not None:
        try:
            return get_json(f"{base_url.rstrip('/')}/{name}.json", timeout=20, retries=2)
        except Exception:
            return None
    return None


def check_health(
    sites: list[dict],
    loader,
    max_fail_hours: float = 48.0,
    max_stale_days: float = 7.0,
    now=None,
) -> tuple[list[str], list[str], str | None]:
    """Return (feed_issues, station_issues, meta_generated_at)."""
    now = now or utcnow()
    meta = loader("meta")
    if not meta:
        return ["`meta.json` is missing or unreadable."], [], None

    feed_issues: list[str] = []
    station_issues: list[str] = []
    meta_sites = meta.get("sites", {})

    for site in sites:
        sid = site["id"]
        site_meta = meta_sites.get(sid, {})
        for source, st in sorted(site_meta.items()):
            if st.get("ok"):
                continue
            fetched_at = st.get("fetched_at")
            if not fetched_at:
                feed_issues.append(f"- **{sid} / {source}**: failing with no previous good data (`{st.get('error', 'unknown error')}`)")
            else:
                age_h = (now - parse_iso(fetched_at)).total_seconds() / 3600
                if age_h >= max_fail_hours:
                    feed_issues.append(
                        f"- **{sid} / {source}**: failing for {age_h:.0f} h (last good: `{fetched_at}`, error: `{st.get('error', 'unknown')}`)"
                    )

        doc = loader(sid)
        if not doc:
            continue
        for st in (doc.get("water") or {}).get("stations", []):
            status = st.get("status")
            if status == "no data":
                station_issues.append(f"- **{sid} / {st['name']}** (`{st['id']}`): no data")
            elif status == "stale":
                latest_t = (st.get("latest") or {}).get("t")
                age_d = (now - parse_iso(latest_t)).total_seconds() / 86400 if latest_t else None
                if age_d is None or age_d >= max_stale_days:
                    age_txt = f"{age_d:.1f} d old" if age_d is not None else "unknown age"
                    station_issues.append(f"- **{sid} / {st['name']}** (`{st['id']}`): stale ({age_txt})")

    return feed_issues, station_issues, meta.get("generated_at")


def format_report(feed_issues: list[str], station_issues: list[str], generated_at: str | None) -> str:
    if not feed_issues and not station_issues:
        return ""
    lines = ["## Field-conditions feed health report", ""]
    if generated_at:
        lines.append(f"Last ingest run: `{generated_at}`")
        lines.append("")
    if feed_issues:
        lines.append("### Failing feeds")
        lines.extend(feed_issues)
        lines.append("")
    if station_issues:
        lines.append("### Stale or empty water stations")
        lines.extend(station_issues)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--max-fail-hours", type=float, default=48.0)
    ap.add_argument("--max-stale-days", type=float, default=7.0)
    ap.add_argument("--out", type=Path, default=None, help="write Markdown report to this file")
    ap.add_argument("--fail-on-issues", action="store_true")
    args = ap.parse_args()

    if args.data_dir is None and args.base_url is None:
        args.data_dir = Path(__file__).parent.parent / "web" / "data"

    feed_issues, station_issues, generated_at = check_health(
        load_sites(),
        lambda name: _load(name, args.data_dir, args.base_url),
        max_fail_hours=args.max_fail_hours,
        max_stale_days=args.max_stale_days,
    )
    report = format_report(feed_issues, station_issues, generated_at)
    if args.out:
        args.out.write_text(report)
    if report:
        print(report)
        return 1 if args.fail_on_issues else 0
    print("All feeds and water stations healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
