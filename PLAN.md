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

- Static site on GitHub Pages. No server, database or secrets. Python standard library only.
- One configuration file, `web/sites.json`, holds everything site-specific.
- Every reading is labeled with its station and the distance from the site, and each site
  page states its known gaps.
- Sites are labeled by water body. Pins mark water bodies, not leases, and farms are not named.
- Metric units throughout.
- A source that fails keeps showing its last good data, with its age visible.
- Values are screened for plausibility only; dropped values are counted and reported.

## Phases

| Phase | Status | Output |
|---|---|---|
| 0. Station audit | Done, Nov 2026 | `docs/station-audit.md`, `web/sites.json` |
| 1. Temperature baselines | Done, Nov 2026 | `web/baseline/*.json`: 2016 to 2025 monthly climatology and yearly summer maxima per site |
| 2. Live site, core variables | Code complete; first live run pending | Map, site, compare, baselines and data pages; hourly ingest of tides, water temperature, salinity, river discharge, weather and rain; archive on the `data` branch |
| 3. More stations, models, satellite, derived metrics | Planned, early 2027 | See below |
| 4. Project data | Planned, before the 2027 field deployment | See below |

### Phase 2, remaining

- First run against the live services, checked site by site.
- Review of `web/sites.json` and the station audit by each node's site lead.

### Phase 3

- Stations not yet wired in: NERRS (CBNERR-VA, NC NERR, Mission-Aransas), VIMS VECOS,
  Chesapeake Bay Program, TWDB and LCRA sondes, NANOOS/IPACOA shellfish stations
  (Whiskey Creek, Bay Center, Nahcotta), WA Ecology.
- Circulation models where no gauge exists in the water body: CBOFS, NGOFS2, WCOFS, LiveOcean.
- Satellite sea-surface temperature and chlorophyll.
- Salinity baselines to match the temperature baselines.
- Derived exposure metrics per site and season: degree-days, days above temperature
  thresholds, low-salinity days and event duration.

### Phase 4

- A slot for the project's own sondes and loggers next to the public stations, so in-gear
  conditions can be compared with the regional record.
- A stable, documented data interface for other project tools to read.
- Versioned snapshots of the archive with a DOI.
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
