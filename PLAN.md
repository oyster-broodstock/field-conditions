# Plan

Where this repository is going and what is already done. Modeled on
[RobertsLab/acantha](https://github.com/RobertsLab/acantha), generalized from one farm to
every field site and hatchery in the project, with the warning layer removed and the focus
on compiling public environmental data.

## Purpose

1. Give every node the same picture of conditions across the Atlantic, Gulf and Pacific sites.
2. Archive the public record permanently, alongside the project's own measurements.
3. Characterize each site by measured exposure (how warm, how fresh, for how long) so that
   treatment effects can be expressed against the environment and not just a place name.
4. Provide historical context, such as local summer maxima, for experimental design.

It is not an advisory service: no flags, thresholds, alerts or harvest-closure information.

## Design choices

- Static site on GitHub Pages. No server, database or secrets. Python standard library only
  for live ingest (gridded model and satellite feeds in Phase 3 should use ERDDAP
  `tabledap`/`griddap` JSON or CSV point queries so live ingest stays stdlib-only; offline
  baseline scripts may use optional packages only if raw NetCDF/OPeNDAP is unavoidable).
- One configuration file, `web/sites.json`, holds everything site-specific (validated on
  every PR by `ci.yml`).
- Every reading is labeled with its station and the distance from the site, and each site
  page states its known gaps.
- Sites are labeled by water body. Pins mark water bodies, not leases, and farms are not named.
- Metric units throughout.
- A source that fails keeps showing its last good data, with its age visible; a weekly
  `health.yml` check opens a GitHub Issue if a feed fails for >48 h or a station is stale >7 d.
- Live values are screened for plausibility only, with dropped values counted and reported.
  Observations are archived daily to the `data` branch (append-only; 30-minute thinning for
  water stations, hourly for USGS/NWS/Stage IV).

## Phases

| Phase | Status | Output |
|---|---|---|
| 0. Station audit | Done, Nov 2026 | `docs/station-audit.md`, `web/sites.json` |
| 1. Temperature baselines | Done, Nov 2026 | `web/baseline/*.json`: 2016 to 2025 monthly climatology and yearly summer maxima per site |
| 2. Live site, core variables | Code complete; first live run pending | Map, site, compare, baselines and data pages; hourly ingest of tides, water temperature, salinity, river discharge, weather and rain; daily archive on the `data` branch; PR validation and weekly feed-health check |
| 3. More stations, models, satellite, derived metrics | Planned, early 2027 | See below |
| 4. Project data | Planned, before the 2027 field deployment | See below |

### Phase 2, remaining

- First run against the live services, checked site by site.
- Review of `web/sites.json` and the station audit by each node's site lead.
- Lock down the archive metadata before Phase 3 adds new platform types: archive a companion
  station metadata snapshot (`stations.csv` or `sites.json` snapshot) on the `data` branch
  with `station_id`, coordinates, `distance_km`, `provider`, and `platform_type` (`station`,
  `model`, `satellite`, `project_sonde`) so historical CSVs remain self-contained.

### Phase 3

Prioritized against the actual site gaps in `docs/station-audit.md`:

- **Tier 1 (zero-data and broken-baseline gaps):**
  - NANOOS/IPACOA shellfish stations: Whiskey Creek Hatchery (Netarts live temperature and
    carbonate chemistry), Bay Center and Nahcotta (Willapa salinity).
  - TWDB and LCRA coastal datasondes (Matagorda/Copano salinity).
  - ORCA buoys or UW LiveOcean (replace Manchester's 2016–2018 Seattle baseline).
- **Tier 2 (closer in-estuary coverage):**
  - NERRS (CBNERR-VA, NC NERR, Mission-Aransas) via ERDDAP mirrors for live data and CDMO
    bulk downloads for historical baselines.
  - VIMS VECOS, Chesapeake Bay Program, and WA Ecology marine stations.
- **Tier 3 (circulation models and satellite):**
  - Circulation models where no gauge exists in the water body: CBOFS, NGOFS2, WCOFS,
    LiveOcean (queried as point time series via ERDDAP).
  - Satellite sea-surface temperature and chlorophyll (NOAA CoastWatch).
- **Salinity baselines** to match the temperature baselines.
- **Derived exposure metrics and QC** per site and season: degree-days, days above
  temperature thresholds, low-salinity days and event duration. Add lightweight QARTOD-style
  spike/flatline flags (so isolated sensor spikes like Garibaldi's 24 °C winter reading are
  not counted as exposure) and pair every exposure metric with a **data coverage percentage**
  so incomplete seasons are not misread as low-stress seasons.

### Phase 4

- A slot for the project's own sondes and loggers next to the public stations, so in-gear
  conditions can be compared with the regional record. Define before deployment:
  - **Ingestion path:** standardized CSV drop-in template (manual upload vs. telemetered
    endpoint) and whether raw logger resolution (e.g., 15-minute) is preserved in the archive.
  - **Privacy and release boundary:** redact logger GPS to water-body coordinates so
    commercial lease locations are never exposed, and specify whether in-gear records are
    published immediately or embargoed until QC.
- A stable, documented data interface for other project tools to read.
- Versioned snapshots of the archive (observations + station metadata) with a DOI.
- Archive format aligned with the project data dictionary.

## Known limits

- Hungars Creek, Topsail Sound and Netarts Bay have no public temperature or salinity gauge
  in the water body itself. Nearest stations are 15 to 35 km away.
- Public real-time salinity is missing for several sites.
- Baselines come from deeper, fixed stations. They describe the regional water mass, not the
  temperature oysters experience in intertidal or floating gear.
- The Netarts and Manchester baselines rest on short or broken records.

Details and station ids are in [`docs/station-audit.md`](docs/station-audit.md).

## Adding a site

Add an entry to `web/sites.json` with coordinates, a tide station, water stations, river
gauges and a baseline station, then run the baseline workflow. No code changes are needed.
