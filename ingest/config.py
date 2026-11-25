"""Shared settings. Sites and stations live in web/sites.json (also read by the web pages)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES_FILE = ROOT / "web" / "sites.json"

# api.weather.gov asks for a User-Agent that identifies the app and a contact.
USER_AGENT = "oyster-broodstock-field-conditions (https://github.com/oyster-broodstock/field-conditions)"
APP = "oyster-broodstock-field-conditions"

TIDE_DAYS = 8            # days of high/low predictions kept
WATER_HOURS = 7 * 24     # history shown on the site (the archive keeps everything)
OBS_HOURS = 72           # weather observations
RAIN_HOURS = 7 * 24
RIVER_DAYS = 7
MAX_AGE_DAYS = 3         # a water station older than this is reported as stale, not dropped


def load_sites() -> list[dict]:
    return json.loads(SITES_FILE.read_text())["sites"]
