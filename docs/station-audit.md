# Station audit

Done 2026-11-25 by querying the live services (NOAA CO-OPS metadata API, IOOS Sensors
ERDDAP search, USGS site service) for stations near each site's water-body coordinates.
Distances are from those coordinates, not from a lease. Re-run the queries when a site's
position is refined.

## Field sites

| Site | Tide predictions | Water temperature | Salinity | River discharge | Baseline record (hourly water temp) |
|---|---|---|---|---|---|
| York River, VA | Gloucester Point 8637624 (0.1 km) | Yorktown USCG 8637689 (3 km) | Yorktown USCG 8637689 | Pamunkey 01673000, Mattaponi 01674500 | Yorktown, 2016–2025, 10 full years |
| Hungars Creek, VA | Cape Charles Harbor 8632366 (16 km, bay side) | Kiptopeke 8632200 (26 km); CBIBS Stingray Point 44058 (31 km) | Kiptopeke (Stingray Point salinity is mis-scaled upstream and dropped) | none gauged | Kiptopeke, 10 years (2023 at 63%) |
| Topsail Sound, NC | Ocean City Beach pier 8657419 (7 km, ocean side) | Wrightsville Beach 8658163 (31 km); UNCW hatchery dock; CORMP ILM2 | UNCW hatchery dock; CORMP ILM2 | NE Cape Fear 02108000 (regional proxy) | Wrightsville Beach, 10 years |
| Corpus Christi Bay, TX | Corpus Christi NAS 8775421 (2 km) | Packery Channel 8775792 (11 km); Ingleside 8775283 (13 km); USS Lexington 8775296 (15 km) | Ingleside 8775283; CBI SALT03 Nueces Bay (its DO feed is mis-scaled and skipped) | Nueces at Calallen 08211500 | Packery Channel, 10 years |
| Matagorda Bay, TX (to be confirmed) | Port O'Connor 8773701 (13 km) | Port O'Connor (13 km); Port Lavaca 8773259 (19 km) | none found | Colorado 08162500, Lavaca 08164000 | Port O'Connor, 8 usable years (2016–2017 partial) |
| Netarts Bay, OR | Netarts 9437262 (1 km) | Garibaldi 9437540 (15 km, Tillamook Bay), via ERDDAP | none found | Wilson 14301500 (regional proxy) | Garibaldi, 4 usable years; many gaps |
| Willapa Bay, WA | Nahcotta 9440747 (8 km) | Toke Point 9440910 (18 km) | none found | Willapa 12013500, Naselle 12010000 | Toke Point, 10 years |

## Hatcheries and broodstock facilities

| Site | Tide predictions | Water temperature | Baseline record |
|---|---|---|---|
| VIMS ABC hatchery, Gloucester Point | Gloucester Point 8637624 | Yorktown USCG 8637689 (3 km; also salinity) | Yorktown, 10 years |
| Texas A&M mariculture facility, Flour Bluff | Packery Channel 8775792 (6 km) | Packery Channel; Bob Hall Pier 8775870 (11 km) | Packery Channel, 10 years |
| ARS broodstock repository, Yaquina Bay | South Beach 9435380 (0.4 km) | South Beach 9435380 | South Beach, 8 usable years (2023 missing) |
| NOAA Manchester Research Station | Clam Bay 9445938 (0.2 km) | Seattle 9447130 (16 km) | Seattle, 2016–2018 only |

## Findings

1. **Three field sites have no public gauge in their own water body**: Hungars Creek,
   Topsail Sound and Netarts Bay. Nearest observations are 15 to 35 km away and in deeper
   or different water. Project sondes are the only way to close this.
2. **Salinity is the thinnest variable.** Public real-time salinity exists near York River,
   Hungars Creek (26 km), Topsail (about 35 km) and Corpus Christi only.
3. **If the second Texas site is Copano Bay**, CO-OPS Copano Bay 8774513 (8 km) and
   Rockport 8774770 (10 km) both report water temperature; Mission and Copano Creek gauges
   (USGS 08189500, 08189200) cover inflow.
4. **Garibaldi's record is unreliable**: under 50% coverage in most years and at least one
   obvious spike (24 °C on 2020-12-28). Whiskey Creek Hatchery data (NANOOS/IPACOA) should
   replace it for Netarts.
5. **Seattle's water temperature record stops in early 2019**, so Manchester has no recent
   baseline. ORCA buoys or LiveOcean are the alternatives.

## Candidates not yet verified or wired in

NERRS CDMO (CBNERR-VA Gloucester Point, Goodwin Islands, Claybank; NC NERR Masonboro Island;
Mission-Aransas Copano Bay), VIMS VECOS, Chesapeake Bay Program stations, TWDB coastal
datasondes, LCRA Matagorda Bay sondes, NANOOS/IPACOA (Whiskey Creek, Bay Center, Nahcotta),
WA Ecology marine stations, NOAA OFS models (CBOFS, NGOFS2, WCOFS), UW LiveOcean, NOAA
CoastWatch SST and chlorophyll.

NERRS web services require a registered IP address, which GitHub-hosted runners cannot
provide; use CDMO bulk downloads for history and an ERDDAP mirror for real time.

## Live check, 2026-11-25

- Garibaldi water temperature was null for the whole previous week, so Netarts Bay currently
  has no live public water temperature at all.
- CBIBS Stingray Point (44058) salinity arrives as about 19847 where about 19.8 is expected.
  The ingest drops values outside a plausible range and says so on the site page.
- TAMU-CC CBI SALT03 (Nueces Bay) dissolved oxygen reads about 0.007 while labeled mg/L.
  That variable is skipped for that station in `web/sites.json`.
