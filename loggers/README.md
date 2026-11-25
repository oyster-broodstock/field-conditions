# Project logger data

Historic and deployment-level sensor files collected directly at project sites
(e.g. Onset HOBO temperature loggers placed in oyster cages).

## Directory layout

Drop raw logger exports into a folder named after the site's `id` in
`web/sites.json`:

```text
loggers/
├── manifest.json                          # optional labels & deployment notes
├── README.md
└── <site_id>/
    └── <logger>_<serial>_<start>_<end>.xlsx   # or .csv
```

> **Privacy note:** Never include exact lease GPS coordinates in filenames,
> `manifest.json`, or logger metadata for commercial sites.

## Supported file formats

`ingest/loggers.py` (Python standard library only) automatically detects:

1. **HOBOconnect `.xlsx` exports** (multi-sheet `Data`, `Events`, `Details`
   workbooks exported directly from the HOBOconnect app).
2. **HOBOconnect `.csv` exports** (`#,Date-Time (PDT/PST),"Temperature , °C"`,
   including trailing event tables and `Details` blocks).
3. **Generic CSVs** with a timestamp column (`datetime_utc`, `timestamp`,
   `date_time`, `datetime`, or `time`) and one or more measurement columns:
   - Water temperature: `water_temp_c`, `temp_c`, `temperature_c`, `temp_f`,
     `temperature` (°F is converted to °C automatically)
   - Salinity: `salinity_psu`, `salinity`
   - Dissolved oxygen: `do_mgl`, `dissolved_oxygen`
   - pH: `ph`

Naive local timestamps are localized using the site's `tz` in `web/sites.json`
and stored as UTC (`YYYY-MM-DDTHH:MM:SSZ`). All values are screened against the
same plausibility ranges as public water stations (`ingest/sources/water.py`).

## Optional metadata (`manifest.json`)

Add an entry keyed by `<site_id>/<filename>` in `loggers/manifest.json` to set
a human-readable `label`, `station_id`, `tz` override, or `notes` (for example,
flagging brief air-exposure spikes during cage checks). Files without a
manifest entry are still ingested automatically.

## Running ingestion

Generate the compact per-site JSON summaries read by `web/site.html`:

```bash
python3 ingest/loggers.py
```

This writes `web/loggers/<site_id>.json` (daily mean/min/max series, monthly
rollups, and deployment metadata).

To also append the full high-frequency readings into the long-format CSV
archive (`archive/<site_id>/<year>.csv`, matching `ingest/archive.py` with
`source=project_logger`):

```bash
python3 ingest/loggers.py --archive-dir ../archive
```
