# Field site conditions

Public environmental data compiled for the grow-out sites and hatcheries of the USDA NIFA
project *Strengthening U.S. Oyster Broodstock Systems* (award 2026-68012-47021).

A static site: no server, no database, no secrets. A scheduled GitHub Actions workflow
fetches public feeds for every site, writes JSON, archives the observations and deploys
to GitHub Pages. Modeled on [RobertsLab/acantha](https://github.com/RobertsLab/acantha),
generalized from one farm to many sites, with the warning layer removed.

It is not an advisory service. There are no flags, thresholds, alerts or harvest-closure
information. Pins mark water bodies, not leases, and farms are not named.

## Pages

| Page | What it shows |
|---|---|
| Map (`index.html`) | All sites, with the latest water temperature, salinity, air temperature and rain near each |
| Site (`site.html?id=...`) | Every feed for one site, each labeled with its station and distance, plus known gaps |
| Compare (`compare.html`) | Latest values for all sites, and 7 days of water temperature and salinity on one chart |
| Baselines (`baselines.html`) | 10-year water temperature climatology and summer maxima per site |
| Data (`about.html`) | Feed status per site, stations used, sources |

## Sites

Seven grow-out sites (York River, Hungars Creek, Topsail Sound, Corpus Christi Bay, a second
Texas site still to be confirmed, Netarts Bay, Willapa Bay) and four hatchery or broodstock
facilities (VIMS ABC, Texas A&M Flour Bluff, ARS Yaquina Bay, NOAA Manchester).

Everything about a site lives in one place, [`web/sites.json`](web/sites.json): coordinates,
tide station, water stations, river gauges, baseline station and a plain statement of known
gaps. **To add or change a site, edit that file.** Nothing else is site-specific.
[`docs/station-audit.md`](docs/station-audit.md) records how the stations were chosen.

## Data sources

| Feed | Source | Notes |
|---|---|---|
| Tide predictions | NOAA CO-OPS | High/low predictions with a cosine curve between them; metres above MLLW |
| Water temperature, salinity | NOAA CO-OPS | 6-minute data thinned to 30 minutes |
| Water temperature, salinity, DO, pH | IOOS Sensors ERDDAP | CBIBS, CORMP, TAMU-CC CBI and other platforms |
| River discharge | USGS Water Services | Provisional; hourly |
| Weather | NWS api.weather.gov | Nearest stations and the forecast grid cell are looked up from the coordinates |
| Rain | NCEP Stage IV via Iowa Environmental Mesonet | Radar and gauge analysis at the site coordinates |

All values are metric. Every station is shown with its distance from the site.

## Archive

The site shows 7 days. Every observation is also appended to the `data` branch as
`archive/<site_id>/<year>.csv`, in long format:

    datetime_utc,site_id,source,station_id,variable,value,unit

Forecasts and tide predictions are not archived.

## Baselines

`baseline/history.py` downloads hourly water temperature (2016 onward) from each site's
baseline station and writes `web/baseline/<site_id>.json`: a monthly climatology and, per
year, the hourly maximum, 99th percentile, warmest 7-day mean and days above 20 to 34 °C.
It is run by hand (Actions tab, "Rebuild temperature baselines"), not on the hourly schedule.

Values are screened only for plausibility (−2 to 40 °C). The 99th percentile and 7-day mean
are robust to sensor spikes; the single hourly maximum is not.

## Run locally

Python 3.10+, standard library only.

    python3 ingest/fetch.py                    # all sites, real data
    python3 ingest/fetch.py --only-sites york  # one site
    python3 serve.py                           # then open http://localhost:8000
    python3 -m unittest discover ingest/tests  # offline tests

    python3 ingest/tests/fake_api.py web/data  # synthetic data for front-end work (red banner)

## Deploy

1. Create the repository and push `main`.
2. Settings > Pages > Source: **GitHub Actions**.
3. The `update.yml` workflow then runs hourly, on every push and on demand.

## Known gaps

- Hungars Creek, Topsail Sound and Netarts Bay have no public temperature or salinity gauge
  in the water body itself. The nearest stations are 15 to 35 km away.
- Salinity is missing for Matagorda Bay, Willapa Bay, Netarts Bay and three of the hatcheries.
- Not yet wired in: NERRS (CBNERR-VA, NC NERR, Mission-Aransas), VIMS VECOS, TWDB and LCRA
  sondes, NANOOS/IPACOA shellfish stations (Whiskey Creek, Bay Center, Nahcotta), WA Ecology,
  circulation models (CBOFS, NGOFS2, LiveOcean) and satellite SST and chlorophyll.
- The project's own sondes and loggers are not included; they are added once deployed.
