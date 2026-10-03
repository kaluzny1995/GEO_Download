← [README](../README.md)

# Data Sources — CSV Field Reference

Every run writes **one CSV per day**, named from the source's `output_file_pattern`
(e.g. `data/GDACS/gdacs_disasters_2026-09-17.csv`).

Conventions shared by every source:

| Convention | Detail |
|------------|--------|
| **Header order** | The order the fields are produced by that source's record builder — `run_download.save_csv()` takes the header from the first record. |
| **Empty cell** | The value was missing or `null` in the API response. Nothing is ever written as `null`. |
| **Date / time** | ISO-8601 exactly as the source returns it (UTC unless the table says otherwise). |
| **Row grain** | One row per event / observation / river-day belonging to that file's date. |
| **No data** | If a source returns nothing for a day, no file is written for that day. A run in which **every** requested day is empty saves no files at all and raises `RuntimeError` (`No files downloaded for <Source>`), ending the process with exit code `1`, so chained steps (ingestion) are not executed. |

## USGS Earthquake

- **File:** `data/USGS_Earthquake/usgs_earthquakes_YYYY-MM-DD.csv` · 23 columns
- **Grain:** one row per seismic event · **Provenance:** passed through unchanged from the USGS FDSN Event Query (`format=csv`), so column names/order are USGS's own.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `time` | ISO-8601 UTC | Origin time (rupture initiation) with milliseconds, e.g. `2026-09-01T23:58:46.050Z` |
| `latitude` | degrees | Epicentre latitude (WGS84 decimal degrees, +north) |
| `longitude` | degrees | Epicentre longitude (WGS84 decimal degrees, +east) |
| `depth` | km | Hypocentre depth below the catalogue datum; small negative values occur for above-datum events |
| `mag` | magnitude | Preferred magnitude of the event — only meaningful together with `magType`; blank if none reported |
| `magType` | code | Method that produced the magnitude: `ml` local/Richter · `md` duration · `mb` short-period body wave (saturates ≈ M6.5) · `ms` 20-s surface wave (≈ M8.3) · `mww`/`mwc`/`mwb` moment (W-phase / centroid / body-wave) · `mwr` regional moment · `mw` generic moment · `mb_lg` Lg regional · `mi` integrated P-wave · `me` energy · `mh` provisional fallback · `mfa` felt-area · `mint` intensity; letter-case varies by network (`ml`/`Ml`), and rare network-specific codes (e.g. `mun`) appear without a USGS definition |
| `nst` | count | Number of stations whose arrivals were used in the location solution; blank when the network doesn't report it |
| `gap` | degrees | Azimuthal gap — largest azimuth sector between azimuthally adjacent stations of the solution (0–360; >180 ⇒ poorly constrained epicentre) |
| `dmin` | degrees | Great-circle distance from the epicentre to the nearest station used (1° ≈ 111.2 km) |
| `rms` | seconds | Root-mean-square travel-time residual (observed − predicted arrivals) — smaller = better fit |
| `net` | code | Network of the preferred origin: `us` USGS NEIC · `ak` Alaska · `ci` Southern California · `nc` Northern California · `ok` Oklahoma · `pr` Puerto Rico · `tx` TexNet · `nn` Nevada · `hv` Hawaii · `av` Alaska Volcano Obs. · `uu` Utah · `uw` Pacific NW · `ld` Lamont-Doherty · `mb` Montana · `nm` New Madrid · `se` Memphis · `at`/`pt` tsunami warning centers |
| `id` | string | Unique ComCat event id = `net` + `code` (e.g. `ci41540448`, `us7000td5z`) — usable as `eventid` and in `earthquake.usgs.gov/earthquakes/eventpage/<id>` |
| `updated` | ISO-8601 UTC | Time the ComCat record was last revised (any product/parameter update) — not the event time |
| `place` | text | Human-readable location, e.g. `9 km WSW of Idyllwild, CA`; Flinn-Engdahl region name for remote events |
| `type` | code | Event type: `earthquake`, `quarry blast`, `explosion`, `mine collapse`, `rock burst`, `collapse`, `landslide`, `snow avalanche`, `ice quake`, `meteor`/`meteorite`, `volcanic eruption`, `sonic boom`, `nuclear explosion`, … |
| `horizontalError` | km | Horizontal location uncertainty — largest error-ellipsoid axis projected on the horizontal plane |
| `depthError` | km | Depth location uncertainty, km; blank if the network supplies no uncertainty estimate |
| `magError` | magnitude units | 1σ standard error of the reported magnitude, valid only for that `magType` (does not include inter-scale bias) |
| `magNst` | count | Number of stations whose amplitude measurements were used to compute the magnitude (often ≠ `nst`) |
| `status` | code | `automatic` = unreviewed machine solution, `reviewed` = human-analyst QC'd (`deleted` exists but is only returned with `includedeleted=only`) |
| `locationSource` | code | Network that originally authored the lat/lon/depth (can differ from `net` when a different origin is preferred) |
| `magSource` | code | Network that originally authored the magnitude (can differ from `net` when a different magnitude is preferred) |

> ℹ **`magType` caveat.** `ci` is a *network* code (Southern California), not a magnitude type — magnitudes from that network usually arrive as `ml`/`md`. USGS enumerates many codes in its API without defining them, so treat unknown codes as network-specific rather than guessing.

## GDACS (Global Disasters)

- **File:** `data/GDACS/gdacs_disasters_YYYY-MM-DD.csv` · 17 columns
- **Grain:** one row per disaster event/episode · **Provenance:** flattened from the GDACS GeoJSON `features[].properties` + `geometry`.
- **Event types:** `EQ` earthquake · `TC` tropical cyclone (hurricane/typhoon) · `FL` flood · `VO` volcanic eruption · `WF` wildfire (forest fire) · `DR` drought. Tsunamis are scored inside the `EQ` model, not published as a separate type. All GDACS timestamps are UTC but are stored **without** an offset.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `event_type` | code | Hazard code: `EQ` earthquake · `TC` tropical cyclone (hurricane/typhoon) · `FL` flood · `VO` volcanic eruption · `WF` wildfire · `DR` drought — tsunamis are reported under `EQ` |
| `event_id` | string | GDACS event id (`eventid`, a plain integer such as `1568573`) — unique only together with `event_type`; the RSS guid concatenates both (e.g. `EQ1568573`) |
| `event_name` | text | Title; pattern varies by type: `Tropical Cyclone NOLO-26`, `Earthquake in Japan`, `Flood in India`, `Forest fires in Australia`, `Eruption  Krakatau`, `Drought in Brazil` |
| `alert_level` | enum | Overall impact alert `Green` / `Orange` / `Red` — hazard × exposed population × country-vulnerability score for EQ/TC/FL (EQ: score ≥2 Red, ≥1 Orange), expert-assessed for VO/WF/DR; older records may differ in case |
| `country` | text | Country/region at the event centroid; may be a region (`South Sandwich Islands Region`), blank for marine cyclones, comma-separated for several |
| `country_code` | ISO-3166 alpha-3 | Affected country (`AUS`, `ESP`, `JPN`); blank when GDACS has none — multi-country events list the rest upstream in `affectedcountries[]` |
| `latitude` | degrees | WGS84 latitude — epicentre for EQ, centroid of the affected-area polygon for the other hazards |
| `longitude` | degrees | WGS84 longitude (GeoJSON stores `[lon, lat]`) |
| `from_date` | ISO UTC (no offset) | Start of the event — EQ origin time, TC/WF first detection, FL/DR window start |
| `to_date` | ISO UTC (no offset) | End / last-validity instant — equal to `from_date` for an instantaneous EQ, latest advisory time for ongoing events |
| `date_modified` | ISO UTC (no offset) | Last GDACS update of this record — the field to compare for incremental refresh |
| `severity` | number | Hazard magnitude whose meaning depends on the type (see `severity_unit`); `0` means "not defined" (VO, most FL) |
| `severity_text` | text | The same value as a sentence, e.g. `Green impact for forestfire in 14196 ha`, `Magnitude 5.4M, Depth:10km` |
| `severity_unit` | unit | `M` moment magnitude (EQ) · `km/h` max sustained wind (TC) · `ha` burned area (WF) · `km2` drought area (DR) · empty for FL (magnitude index) and VO (severity unused) |
| `source` | code | Contributing body: `NEIC`/`EMSC` (EQ) · `NOAA`/`JTWC`/`RSMC` (TC) · `GLOFAS`/`DFO` (FL) · `GWIS` (WF) · `GDO` (DR) · VAAC names (`TOKYO`, `DARWIN`, `WASHINGTON`, …) and `JRC` (VO) |
| `report_url` | URL | GDACS report page for the event, e.g. `https://www.gdacs.org/report.aspx?eventid=1001325&episodeid=35&eventtype=TC` |
| `is_current` | `true` / `false` | Whether GDACS still treats the event as ongoing — observed `true` only while `to_date` lies within the last ~4 days (EQ/TC/FL/WF); VO and DR records stay `false` even while still updating |

## NASA EONET (Natural Events)

- **File:** `data/EONET/eonet_events_YYYY-MM-DD.csv` · 17 columns
- **Grain:** one row per EONET event · **Provenance:** flattened from `events[]`.
- **Categories:** `wildfires`, `severeStorms`, `floods`, `volcanoes`, `earthquakes`, `drought`, `landslides`, `seaLakeIce`, `snow`, `tempExtremes`, `dustHaze`, `manmade`, `waterColor`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `event_id` | string | EONET event `id`, unique per event, e.g. `EONET_24483` |
| `event_name` | text | Event `title` verbatim, e.g. `Wildfire Breezy, Starr, Texas` |
| `category_id` | code | **First** category only (`categories[0]` — an event may carry several): `wildfires`, `severeStorms`, `floods`, `volcanoes`, `earthquakes`, `drought`, `landslides`, `seaLakeIce`, `snow`, `tempExtremes`, `dustHaze`, `manmade`, `waterColor` |
| `category_name` | text | Title of that first category (`Wildfires`, `Sea and Lake Ice`, …) |
| `description` | text | Optional event `description` — "a sentence or two", usually a location (`7 Miles NE from Rio Grande City, TX`); `null` → blank |
| `source_id` | code | **First** source id (`sources[0]`) — `IRWIN`, `InciWeb`, `JTWC`, `NOAA_NHC`, `GDACS`, `USGS_EHP`, `SIVolcano`, `CEMS`, `EO`, `Earthdata`, `FEMA`, … (full list: `/api/v3/sources`) |
| `source_url` | URL | That source's own link to further information (not an EONET URL) |
| `latitude` | degrees | Latitude of the **first** geometry (`geometry[0]`) — for Polygon geometries this is the first ring vertex, so it is only meaningful for point events |
| `longitude` | degrees | Longitude of the first geometry (GeoJSON order is `[lon, lat]`) |
| `event_date` | ISO-8601 UTC | Timestamp of the first geometry — usually `00:00Z` unless the source supplied a time |
| `magnitude_value` | number | `magnitudeValue` of that first geometry, if the source supplied one; empty otherwise |
| `magnitude_unit` | unit | Unit of that magnitude: `acres`/`hectare` burned area · `kts` average max sustained wind · `NM^2` ice area · `Mw/Mww`, `Mb`, `Ml`, `Mi/Mwp`, `Mwb`, `Mwc`, `Mwr` earthquake magnitudes (catalogue: `/api/v3/magnitudes`) |
| `closed` | ISO-8601 UTC | When the event ended — per NASA "may or may not accurately represent the absolute ending"; `null` while open (EONET returns open events by default, so this is normally blank) |
| `geometry_count` | count | Number of dated geometries: 1 = single fix, N = track/history of the event |
| `last_latitude` | degrees | Latitude of the **last** geometry (most recent fix — geometries are observed in ascending date order, though NASA doesn't document that guarantee) |
| `last_longitude` | degrees | Longitude of the last geometry |
| `last_date` | ISO-8601 UTC | Timestamp of the most recent geometry |

## Open-Meteo Flood (River Discharge)

- **File:** `data/OpenMeteo_Flood/openmeteo_rivers_YYYY-MM-DD.csv` · 6 columns
- **Grain:** one row per river per day · **Coverage:** 126 major rivers from `data/rivers.json` (Copernicus GloFAS model, 0.05°/~5 km grid); days with `null` discharge are skipped. Values are **modelled estimates**, not gauge measurements.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `river_name` | text | River label read from local `data/rivers.json` (`Amazon`, `Paraná`, …) — the Flood API returns no river name |
| `country` | text | Country of the reference point as recorded in `rivers.json` (not returned by the API) |
| `latitude` | degrees | WGS84 latitude of the reference point queried from `rivers.json`; the GloFAS cell actually used is the nearest 0.05° (~5 km) grid cell and may differ slightly |
| `longitude` | degrees | WGS84 longitude of the reference point (same grid caveat as `latitude`) |
| `date` | `YYYY-MM-DD` | GMT+0 calendar day of the value — the GloFAS 24-h mean from 00:00 to 00:00 UTC |
| `discharge_m3s` | m³/s | Simulated daily river discharge, 24-h mean in m³/s (e.g. `77982.05` for the Amazon) — GloFAS historical analysis + forecast, so the value is a model output, not an observation |

## USGS NWIS (US Streamflow)

- **File:** `data/USGS_NWIS/usgs_streamflow_YYYY-MM-DD.csv` · 9 columns
- **Grain:** one row per gauge per day · **Defaults:** site `01646500` (Potomac River near Washington DC), parameter `00060` (discharge) — both configurable via `sites` / `parameter_code`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `site_id` | string | `USGS-` + NWIS site number, e.g. `USGS-01646500` (8-digit surface-water gauge, 15-digit groundwater; matches the modern `monitoring_location_id`) |
| `site_name` | text | Official NWIS station name, e.g. `POTOMAC RIVER NEAR WASH, DC LITTLE FALLS PUMP STA` |
| `parameter_code` | code | 5-digit NWIS parameter code — `00060` = "Discharge, cubic feet per second"; the daily statistic is `00003` Mean (the statistic is not stored in this CSV) |
| `date` | `YYYY-MM-DD` | Day of the value in the **site's local time zone** (truncated from the API's `dateTime`) |
| `value` | number | Daily value for that day (the mean when the statistic is `00003`) |
| `unit` | unit | `ft3/s` for parameter `00060`; metric discharge is a *separate* parameter code (`99060`, m³/s), not a unit option |
| `qualifiers` | flags | NWIS quality codes joined with `,`: `A` approved for publication · `P` provisional, subject to revision · `e` estimated · `R` revised · `p` partial record · `Bkw` backwater · `Eqp` equipment malfunction · `Rat` rating being developed · `Ssn` monitored seasonally · `ZFL` zero flow · `***` value unavailable |
| `latitude` | degrees | Gauge latitude, decimal degrees (EPSG:4326) |
| `longitude` | degrees | Gauge longitude, decimal degrees (EPSG:4326) |

## Avalanche.org (US Avalanche Forecasts)

- **File:** `data/Avalanche_ORG/avalancheorg_avalanche_YYYY-MM-DD.csv` · 16 columns
- **Grain:** one row per forecast zone per day · **Coverage:** 28 US avalanche centers / 82+ zones; the map-layer endpoint is queried once per day.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `zone_id` | integer | Forecast-zone GeoJSON feature id (stable per zone, not reused) |
| `zone_name` | text | Forecast-zone name as published by the center (equals the center name for single-zone centers) |
| `center_id` | code | Issuing avalanche center's acronym, e.g. `BAC` Bridgeport, `NWAC`, `UAC`, `CAIC`, `GNFAC`, `SAC`, `BTAC`, `MWAC` |
| `center_name` | text | Full center name, e.g. `Bridgeport Avalanche Center` |
| `state` | 2-letter code | US state the zone polygon lies in (`CA`, `CO`, …); some zones cross state lines |
| `danger_level` | `-1` … `5` | North American Public Avalanche Danger Scale: `-1` no rating, `1` low, `2` moderate, `3` considerable, `4` high, `5` extreme |
| `danger_rating` | text | Same rating as text: `no rating`, `low`, `moderate`, `considerable`, `high`, `extreme` |
| `travel_advice` | text | The standard scale sentence for that rating (identical across centers, not center-authored prose); generic advice when unrated — e.g. level 3: `Dangerous avalanche conditions. Careful snowpack evaluation, cautious route-finding and conservative decision-making essential.` |
| `off_season` | `True` / `False` | `True` = zone is out of its forecast season (the map shows "Forecasts ended for the season", greys the polygon and links the center homepage) |
| `forecast_start` | ISO local datetime | When the forecast was issued (`start_date`) — shown as "Valid: …" in the center's own timezone; empty when unrated |
| `forecast_end` | ISO local datetime | When the forecast expires (`end_date`) — typically ~24 h after `forecast_start`, longer for weekly/monthly publishers |
| `warning` | text | `warning.product` = `warning` while an Avalanche Warning covers the zone (the most severe alert: large avalanches certain/very likely, or High/Extreme danger expected); otherwise empty |
| `link` | URL | The zone's forecast page on the center site (falls back to the center homepage when off-season or archived) |
| `latitude` | degrees | Area weighted centroid of the zone polygon, rounded to 6 decimals (WGS84); empty when the feature has no usable geometry |
| `longitude` | degrees | Same centroid, longitude |
| `date` | `YYYY-MM-DD` | Day that was queried — added by the downloader, not present in the API response (matches the API's `?day=` archive parameter) |

> ℹ **Zone centroid lookup.** Every centroid is also merged into the consolidated lookup `data/avalanche_org_notices.csv` (`place_location, state, latitude, longitude`, one row per zone keyed zone name + state, sorted by state). Existing rows are kept when a zone disappears from the feed, so zones that leave the daily map stay covered.

> ℹ **Danger scale (NAPADS).** 1 *Low* — generally safe; watch for unstable snow on isolated features.
> 2 *Moderate* — heightened conditions on specific terrain features; evaluate carefully.
> 3 *Considerable* — dangerous; careful snowpack evaluation and conservative decisions essential (historically the deadliest level).
> 4 *High* — very dangerous; travel in avalanche terrain not recommended.
> 5 *Extreme* — extraordinarily dangerous; avoid all avalanche terrain.
> Every level carries the banner: *Safe backcountry travel requires training and experience. You control your own risk by choosing where, when and how you travel.*

## IBTrACS (Global Tropical Cyclones)

- **File:** `data/IBTrACS/ibtracs_cyclones_YYYY-MM-DD.csv` · **174 columns**
- **Grain:** one row per cyclone position (best-track point) · **Provenance:** NOAA IBTrACS v04r01 (`last3years` by default), streamed row-by-row; the upstream *units* row (row 2) is discarded and only rows whose `ISO_TIME` falls inside the requested day are kept.
- `ISO_TIME` is looked up **by header name**, never by a fixed column index — the live header starts `SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,…`, so any positional assumption silently filters out every row.
- The upstream `last3years` file trails the present by 1–2 days, so the most recent days can legitimately yield no rows (and therefore no file); the next incremental run retries them.
- Missing values are blank cells (IBTrACS's own convention).

### Core columns (19)

| Column | Unit | Description |
|--------|------|-------------|
| `SID` | string | IBTrACS serial id (13 chars): 4-digit year + 3-digit day-of-year of genesis + `N`/`S` + 2-digit rounded genesis lat + 3-digit rounded genesis lon in °E (0–360), e.g. `2026254N11252` — *not* the ATCF id (that is `USA_ATCF_ID`) |
| `SEASON` | year | Year in which the storm began; Southern-Hemisphere seasons count storms starting after 1 July in the following year |
| `NUMBER` | integer | Storm number within `SEASON` (restarts at 1 each year) — numbered across **all** basins, so numbers are not continuous in a single-basin file |
| `BASIN` | code | Basin of this position: `NA` North Atlantic · `EP` Eastern North Pacific · `WP` Western North Pacific · `NI` North Indian · `SI` South Indian · `SP` South Pacific · `SA` South Atlantic · `MM` missing |
| `SUBBASIN` | code | Sub-basin of this position: `CS` Caribbean Sea · `GM` Gulf of Mexico · `CP` Central Pacific · `AS` Arabian Sea · `BB` Bay of Bengal · `WA` Western Australia · `EA` Eastern Australia · `NA` North Atlantic (no sub-basin) · `MM` none/default |
| `NAME` | string | Storm name as supplied by the agency (IBTrACS drops most names containing digits/abbreviations); blank when unnamed |
| `ISO_TIME` | UTC datetime | Observation time `YYYY-MM-DD HH:MM:SS` — normally 6-hourly, but 3-hourly (IMD) and non-synoptic times (landfall, intensity peaks) also occur — **the column the downloader filters on** |
| `NATURE` | code | Combined storm type across agencies: `DS` disturbance · `TS` tropical · `ET` extratropical · `SS` subtropical · `NR` not reported · `MX` contradictory reports |
| `LAT` | deg north | Merged best-track latitude, 0.1° resolution (negative = south) |
| `LON` | deg east | Merged best-track longitude, 0.1° resolution (negative = west) |
| `WMO_WIND` | knots | Maximum sustained wind from the basin's responsible WMO agency, **not** homogenised: US 1-min, India 3-min, Japan/Australia/La Réunion/Nadi/Wellington 10-min averaging |
| `WMO_PRES` | mb | Minimum central pressure assigned by the responsible WMO agency for this location |
| `WMO_AGENCY` | code | WMO centre responsible for warnings at this point, e.g. `hurdat_atl`, `atcf`, `tokyo`, `newdelhi`, `reunion`, `bom`, `nadi`, `wellington` |
| `TRACK_TYPE` | code | `MAIN` reanalysed primary track · `spur` interaction/alternate-position track · `PROVISIONAL` / `US-PROVISIONAL` real-time data still awaiting reanalysis (plus their `_spur` variants) |
| `DIST2LAND` | km | Distance from the centre to the nearest land (land mask = continents + islands > 1400 km²) |
| `LANDFALL` | km | Minimum distance to land between this position and the **next** timestep (usually 3 h); `0` = landfall within 3 h; < 60 nm ⇒ likely impacts |
| `IFLAG` | 15 chars | One provenance/interpolation char per source dataset, in fixed order (USA, Tokyo, CMA, HKO, KMA, NewDelhi, Reunion, BoM, Nadi, Wellington, ds824, TD9636, TD9635, Neumann, Chenoweth): `_` none · `O` original · `P` fully interpolated · `I` intensity filled · `V` partly filled |
| `STORM_SPEED` | knots | Translation speed derived by IBTrACS from successive `LAT`/`LON` positions |
| `STORM_DIR` | degrees | Direction of motion, degrees clockwise from north (0–360, rounded to 5°), computed from `LAT`/`LON` |

### Agency columns (155)

Each agency column is `<PREFIX>_<SUFFIX>` and holds the value **as reported by that agency**; it is blank when that agency did not report the value.

| `<PREFIX>` | Reporting agency / dataset | Suffixes available |
|------------|----------------------------|--------------------|
| `USA` | US agencies / NHC (ATCF + HURDAT2) | `AGENCY`, `ATCF_ID`, `LAT`, `LON`, `RECORD`, `STATUS`, `WIND`, `PRES`, `SSHS`, `R34_NE`, `R34_SE`, `R34_SW`, `R34_NW`, `R50_NE`, `R50_SE`, `R50_SW`, `R50_NW`, `R64_NE`, `R64_SE`, `R64_SW`, `R64_NW`, `POCI`, `ROCI`, `RMW`, `EYE`, `GUST`, `SEAHGT`, `SEARAD_NE`, `SEARAD_SE`, `SEARAD_SW`, `SEARAD_NW` |
| `TOKYO` | RSMC Tokyo (JMA) | `LAT`, `LON`, `GRADE`, `WIND`, `PRES`, `R50_DIR`, `R50_LONG`, `R50_SHORT`, `R30_DIR`, `R30_LONG`, `R30_SHORT`, `LAND` |
| `CMA` | China Meteorological Administration | `LAT`, `LON`, `CAT`, `WIND`, `PRES` |
| `HKO` | Hong Kong Observatory | `LAT`, `LON`, `CAT`, `WIND`, `PRES` |
| `KMA` | Korea Meteorological Administration | `LAT`, `LON`, `CAT`, `WIND`, `PRES`, `R50_DIR`, `R50_LONG`, `R50_SHORT`, `R30_DIR`, `R30_LONG`, `R30_SHORT` |
| `NEWDELHI` | RSMC New Delhi (IMD) | `LAT`, `LON`, `GRADE`, `WIND`, `PRES`, `CI`, `DP`, `POCI` |
| `REUNION` | RSMC La Réunion (MFR) | `LAT`, `LON`, `TYPE`, `WIND`, `PRES`, `TNUM`, `CI`, `RMW`, `R34_NE`, `R34_SE`, `R34_SW`, `R34_NW`, `R50_NE`, `R50_SE`, `R50_SW`, `R50_NW`, `R64_NE`, `R64_SE`, `R64_SW`, `R64_NW`, `GUST`, `GUST_PER` |
| `BOM` | Australian TCWCs (BOM) | `LAT`, `LON`, `TYPE`, `WIND`, `PRES`, `TNUM`, `CI`, `RMW`, `R34_NE`, `R34_SE`, `R34_SW`, `R34_NW`, `R50_NE`, `R50_SE`, `R50_SW`, `R50_NW`, `R64_NE`, `R64_SE`, `R64_SW`, `R64_NW`, `ROCI`, `POCI`, `EYE`, `POS_METHOD`, `PRES_METHOD`, `GUST`, `GUST_PER` |
| `NADI` | RSMC Nadi (FMS) | `LAT`, `LON`, `CAT`, `WIND`, `PRES` |
| `WELLINGTON` | TCWC Wellington (NZMS) | `LAT`, `LON`, `WIND`, `PRES` |
| `DS824` | NCEI dataset DS824 | `LAT`, `LON`, `STAGE`, `WIND`, `PRES` |
| `TD9636` | NCEI dataset TD9636 | `LAT`, `LON`, `STAGE`, `WIND`, `PRES` |
| `TD9635` | NCEI dataset TD9635 | `LAT`, `LON`, `WIND`, `PRES`, `ROCI` |
| `NEUMANN` | C. Neumann southern-hemisphere dataset | `LAT`, `LON`, `CLASS`, `WIND`, `PRES` |
| `MLC` | M. Chenoweth Atlantic historical dataset | `LAT`, `LON`, `CLASS`, `WIND`, `PRES` |

### Suffix glossary

| Suffix | Unit | Meaning |
|--------|------|---------|
| `_AGENCY` | — | WMO centre responsible at this point (`WMO_AGENCY`); for `USA_AGENCY` the selected US source in priority order (`hurdat_atl`, `hurdat_epa`, `atcf`, `jtwc_*`, `cphc`; `tcvitals`/`tcvightals` = preliminary vitals) |
| `_ATCF_ID` | — | US ATCF storm id `bb`+`nn`+`yyyy` (e.g. `AL092026`; basins AL, SL, EP, WP, SH, IO); several ids joined by `:` |
| `_LAT` | deg north | Latitude reported by this agency (unmerged; negative = south) |
| `_LON` | deg east | Longitude reported by this agency (negative = west) |
| `_RECORD` | — | HURDAT/ATCF record flag: `G` genesis · `L` landfall · `I` intensity peak · `P` min pressure · `W` max wind · `S` status change · `T` track detail · `R` rapid change · `C` closest approach to coast (no landfall); blank = none |
| `_STATUS` | — | 2-char system status: `DB` disturbance · `TD` tropical depression · `TS` tropical storm · `TY` typhoon · `ST` super typhoon · `TC` tropical cyclone · `HU`/`HR` hurricane · `SD` subtropical depression · `SS` subtropical storm · `EX` extratropical · `PT` post-tropical · `IN` inland · `DS` dissipating · `LO` low · `WV` tropical wave · `ET` extrapolated · `MD` monsoon depression · `XX` unknown |
| `_WIND` | knots | Agency maximum sustained wind — averaging period differs by source (US 1-min, CMA 2-min, IMD 3-min, others 10-min) and is **not** homogenised |
| `_PRES` | mb | Minimum/central pressure as reported by that agency |
| `_SSHS` | category | Saffir-Simpson category from US 1-min wind: `5` ≥137 kt · `4` 113–136 · `3` 96–112 · `2` 83–95 · `1` 64–82 · `0` TS 34–63 · `−1` TD <34 · `−2` subtropical · `−3` disturbance · `−4` post-tropical · `−5` unknown |
| `_R34_NE` | nmile | 34 kt wind radii, maximum extent NE quadrant |
| `_R34_SE` | nmile | 34 kt wind radii, maximum extent SE quadrant |
| `_R34_SW` | nmile | 34 kt wind radii, maximum extent SW quadrant |
| `_R34_NW` | nmile | 34 kt wind radii, maximum extent NW quadrant |
| `_R50_NE` | nmile | 50 kt wind radii, maximum extent NE quadrant |
| `_R50_SE` | nmile | 50 kt wind radii, maximum extent SE quadrant |
| `_R50_SW` | nmile | 50 kt wind radii, maximum extent SW quadrant |
| `_R50_NW` | nmile | 50 kt wind radii, maximum extent NW quadrant |
| `_R64_NE` | nmile | 64 kt wind radii, maximum extent NE quadrant |
| `_R64_SE` | nmile | 64 kt wind radii, maximum extent SE quadrant |
| `_R64_SW` | nmile | 64 kt wind radii, maximum extent SW quadrant |
| `_R64_NW` | nmile | 64 kt wind radii, maximum extent NW quadrant |
| `_POCI` | mb | Pressure of the outermost closed isobar (BOM: environmental pressure) |
| `_ROCI` | nmile | Radius of the outermost closed isobar |
| `_RMW` | nmile | Radius of maximum winds |
| `_EYE` | nmile | `USA_EYE` = eye **diameter**; `BOM_EYE` = mean eye **radius** — the two definitions differ |
| `_GUST` | knots | Maximum wind gust: `USA_GUST` as reported, `BOM_GUST` open-terrain estimate near the centre, `REUNION_GUST` |
| `_SEAHGT` | ft | Wave height used with the `SEARAD` radii |
| `_SEARAD_NE` | nmile | Radial extent of those seas NE of the centre |
| `_SEARAD_SE` | nmile | Radial extent of those seas SE of the centre |
| `_SEARAD_SW` | nmile | Radial extent of those seas SW of the centre |
| `_SEARAD_NW` | nmile | Radial extent of those seas NW of the centre |
| `_GRADE` | — | Source intensity grade: JMA 1–9 (`2` TD, `3` TS, `4` STS, `5` TY, `6` extratropical, `7` entering the JMA area, `9` ≥ TS; 1 and 8 unused) or IMD grade (`D`, `DD`, `CS`, `SCS`, `VSCS`, `ESCS`, `SuCS`) |
| `_R50_DIR` | degrees | Direction code of the shortest 50 kt wind radius (JMA: 1 NE, 2 E, 3 SE, 4 S, 5 SW, 6 W, 7 NW, 8 N, 9 symmetric circle; KMA uses the same names for **25 m/s** winds) |
| `_R50_LONG` | nmile | Longest radius of 50 kt (25 m/s for KMA) winds or greater |
| `_R50_SHORT` | nmile | Shortest radius of 50 kt (25 m/s for KMA) winds or greater |
| `_R30_DIR` | degrees | Direction code of the shortest 30 kt wind radius (JMA; KMA same names for **15 m/s** ≈ 30 kt) |
| `_R30_LONG` | nmile | Longest radius of 30 kt (15 m/s for KMA) winds or greater |
| `_R30_SHORT` | nmile | Shortest radius of 30 kt (15 m/s for KMA) winds or greater |
| `_LAND` | flag | JMA: `1` = landfall or passage over the Japanese islands within **1 hour** after this analysis time, `0` otherwise |
| `_CAT` | category | Agency intensity category: CMA 0–6/9 (TD/TS/STS/TY/STY/SuperTY, 9 = extratropical), HKO (`LW`/`TD`/`TS`/`STS`/`T`/`ST`/`SuperT`), KMA (`TD`/`TS`/`STS`/`TY`/`L`), NADI numeric |
| `_CI` | Dvorak CI# | Dvorak current-intensity number — T/CI scale 1.0–8.0 in 0.5 steps (≈25–170 kt); CI 2.5 ≈ 35 kt, CI 4.0 ≈ 65 kt |
| `_DP` | mb | `NEWDELHI_DP` = central **pressure deficit / pressure fall** at the centre (IMD Dvorak pressure drop), *not* a Dvorak pressure |
| `_TYPE` | — | Agency storm type: `REUNION_TYPE` 01–09/99 (01 disturbance with no closed isobar … 05 extratropical, 06 dissipating, 07 subtropical, 08 overland), `BOM_TYPE` ADAM/WMO codes |
| `_TNUM` | Dvorak T# | Dvorak pattern T-number, same 1.0–8.0 / 0.5 scale; equals or trails CI while the storm develops (CI lags when it weakens) |
| `_GUST_PER` | seconds | Gust averaging period (BoM gusts are 3-s; the field only appears for non-3-s WMO input) |
| `_POS_METHOD` | — | BOM ADAM code for how the centre position was derived (1 no sat/rad/obs … 4 clear eye in IR/Vis, 8 report inside eye, 13 UAV) |
| `_PRES_METHOD` | — | BOM ADAM code for the pressure source (1 aircraft/dropsonde, 4 instrument unknown, 5 from Dvorak, 6 derived from wind, 8 radar extrapolation) |
| `_STAGE` | — | Stage/intensity code: `DS824_STAGE` `DS` disturbance · `WV` wave · `TC` tropical cyclone · `EX` extratropical · `MM` missing; `TD9636_STAGE` 0–7 (0 disturbance, 1 depression <34 kt, 2 storm 34–63 kt, 3 ≥64 kt, 4 hurricane, 5 extratropical, 6 dissipating, 7 doubtful) |
| `_CLASS` | — | Agency class: `TC` tropical, `EX` extratropical, `MM` missing (the Chenoweth `MLC` dataset also uses `TD`, `TS`, `HU`, `MH`, `SD`, `SS`, `LO`, `WV`) |

_File total: **174 columns** = 19 core + 155 agency._

## USGS Volcano

- **File:** `data/USGS_Volcano/usgs_volcanoes_YYYY-MM-DD.csv` · 11 columns
- **Grain:** one row per notice for an elevated volcano · **Coverage:** only volcanoes above `NORMAL` alert (ADVISORY / WATCH / WARNING), filtered to notices issued inside the requested day.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `volcano_name` | text | Volcano name (Smithsonian GVP primary name), e.g. `Ahyi Seamount`, `Kilauea` — one notice can cover several volcanoes |
| `vnum` | integer | Smithsonian Global Volcanism Program volcano number — permanent 6-digit id, e.g. `284141` Ahyi, `332010` Kīlauea |
| `observatory` | code | Issuing USGS volcano observatory: `avo` Alaska · `calvo` California · `cvo` Cascades · `hvo` Hawaiian · `nmi` Northern Mariana Islands · `yvo` Yellowstone |
| `observatory_name` | text | Full observatory name, e.g. `Alaska Volcano Observatory` |
| `alert_level` | enum | Volcano Alert Level (ground hazards): `NORMAL` background · `ADVISORY` elevated unrest above background · `WATCH` heightened/escalating unrest or an eruption with limited hazards · `WARNING` hazardous eruption imminent, underway or suspected (`UNASSIGNED` = too poorly monitored to classify — this file only holds the three above-`NORMAL` levels) |
| `color_code` | enum | Aviation Color Code: `GREEN` background · `YELLOW` elevated unrest · `ORANGE` escalating unrest or eruption with no/minor ash · `RED` imminent or ongoing eruption with significant ash (+ `UNASSIGNED`); developed by AVO, standardised in ICAO Doc 9766 |
| `notice_type` | code | HANS notice type: `DU` daily · `WU` weekly · `MU` monthly · `BU` biweekly update · `VAN` volcano activity notification (alert-level changes) · `VV` VONA — Volcano Observatory Notice for Aviation · `SR` status report · `IS` information statement |
| `notice_identifier` | string | Globally unique notice id `DOI-USGS-<OBS>-<ISO-8601>`, e.g. `DOI-USGS-NMI-2026-09-10T23:17:05+00:00` |
| `notice_date` | `YYYY-MM-DD HH:MM:SS` UTC | Time the notice was sent (`sent_utc`) — this is what the day filter uses |
| `notice_url` | URL | Public notice page: `https://volcanoes.usgs.gov/hans-public/notice/<notice_identifier>` |
| `notice_data_url` | URL | HANS API endpoint with the notice content as JSON/HTML: `…/hans-public/api/notice/getNotice/<notice_identifier>` |

## NIFC (US Wildland Fires)

- **File:** `data/NIFC/nifc_fires_YYYY-MM-DD.csv` · 17 columns
- **Grain:** one row per fire-perimeter feature updated inside the day · **Provenance:** ArcGIS FeatureServer `attributes` from the WFIGS *Interagency Perimeters* layer — polygon geometry is not requested, but the feature **centroid** is (`returnCentroid=true`), which supplies `latitude`/`longitude`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `incident_name` | text | Fire / incident name copied from the source polygon (`poly_IncidentName`, ≤50 chars) |
| `irwin_id` | GUID | IRWIN incident identifier — 38-char braced GUID `{66CFAACE-3C03-…}`, one per incident, repeated on every perimeter of that fire |
| `fire_number` | epoch ms | **Named misleadingly** — it holds the fire discovery date/time (`attr_FireDiscoveryDateTime`), Unix **milliseconds** UTC; empty when unreported |
| `acres` | acres | Perimeter acreage stored on the source polygon (`poly_GISAcres`) — that polygon's own GIS figure, which can differ from IRWIN's reported incident size |
| `percent_contained` | % | Percent of the incident area no longer active (`attr_PercentContained`, 0–100) — an ICS-209 incident-reporting value mirrored onto every perimeter, so it lags and is independent of the polygon geometry |
| `fire_type` | code | IRWIN incident type category (`attr_IncidentTypeCategory`) — this layer only ever serves `WF` wildfire and `RX` prescribed fire; upstream IRWIN also defines `CX` complex, `DF` debris, `SF` structure, `VF` vehicle, `NS`, `SU`, `PP`, `FA`, `OR`, `BR`, `FR` |
| `fire_type_label` | text | Perimeter feature category (`poly_FeatureCategory`) from the NWCG Wildland Fire Event Polygon standard — this layer serves *Wildfire Daily Fire Perimeter* and *Prescribed Fire*; the standard also allows *Wildfire Final Fire Perimeter*, *Unburned Island*, *Unknown*, … |
| `jurisdiction` | code | Point-of-origin jurisdictional agency (`attr_POOJurisdictionalAgency`) — the agency with land-management responsibility for the origin land: `USFS`, `BLM`, `BIA`, `NPS`, `USFWS`, `DNR`, `SF`, `SFS`, … empty when unset |
| `jurisdiction_label` | code | NWCG unit id of that land (`attr_POOJurisdictionalUnit`) with the leading `US` stripped — 2-letter state + 3–4-char unit code, e.g. `WAOWF` Okanogan-Wenatchee NF, `ORUMF` Umatilla NF, `CAYNP` Yosemite NP — a *code*, not a name |
| `unit_name` | text | Full name of `jurisdiction_label` resolved at download time through the consolidated lookup `data/nifc_unit_names.csv` (`WAOWF` → `Okanogan-Wenatchee National Forest`); a code the lookup does not know keeps its raw value, a blank code stays empty |
| `state` | 2-letter code | Point-of-origin state (`attr_POOState`) with the `US-` prefix stripped |
| `po_method` | code | **Named misleadingly** — the raw IRWIN point-of-origin state code (`attr_POOState`, `US-CO`), i.e. the unstripped source of `state` |
| `latitude` | degrees | Perimeter **centroid** latitude (`returnCentroid=true`, WGS84); falls back to `attr_InitialLatitude` (point of origin) when the service omits it |
| `longitude` | degrees | Perimeter centroid longitude (same fallback: `attr_InitialLongitude`) |
| `poly_date` | epoch ms | When the source polygon record was last edited, Unix ms UTC (`poly_DateCurrent`) — the field the day query filters on |
| `created_on` | epoch ms | When the IRWIN incident record was created (`attr_CreatedOnDateTime_dt`), Unix ms UTC |
| `modified_on` | epoch ms | When the IRWIN incident record was last modified (`attr_ModifiedOnDateTime_dt`), Unix ms UTC — can be newer than `poly_date` |

> ℹ **Layer-specific field names.** On the *Perimeters* layer `poly_*` are perimeter
> attributes and `attr_*` are incident attributes mirrored onto each perimeter — every
> name in the request must exist in that schema. ArcGIS rejects an unknown `outFields`
> list with **HTTP 200** plus `{"error":{"code":400,…,"details":["'outFields' parameter is invalid"]}}`,
> which reads as "0 records" rather than as a failure. This source silently produced no
> files from 2026-09-18 until 2026-09-26, when the columns were re-mapped to real field
> names and the downloader started logging `error` payloads (`NIFC API rejected the query: …`).
> The layer exposes no human-readable agency name, hence `jurisdiction_label` holds a unit *code*.
>
> ℹ **Unit-name lookup.** The downloader resolves that code into `unit_name` through the
> consolidated lookup `data/nifc_unit_names.csv` (`unit_code, unit_name`, one row per unit,
> sorted by code), built when missing and refreshed from the public
> [`DMP_JurisdictionalUnits_Public`](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/DMP_JurisdictionalUnits_Public/FeatureServer/0/query)
> layer whenever the data carries a code the file does not know — one request per refresh,
> so the ETL reads the full name straight from the source row.
>
> Fields a query must not omit: `poly_IncidentName`, `poly_IRWINID`, `poly_FeatureCategory`,
> `poly_GISAcres`, `poly_DateCurrent`, `attr_IncidentTypeCategory`, `attr_FireDiscoveryDateTime`,
> `attr_PercentContained`, `attr_POOJurisdictionalAgency`, `attr_POOJurisdictionalUnit`,
> `attr_POOState`, `attr_InitialLatitude`, `attr_InitialLongitude`,
> `attr_CreatedOnDateTime_dt`, `attr_ModifiedOnDateTime_dt` — kept in
> `NIFCDownloader._OUT_FIELDS` (downloader/nifc.py).

## Reference documentation

Every description above is drawn from the source's own documentation (consulted
2026-09-29); code vocabularies were cross-checked against the CSVs this repo
actually produces:

| Source | Official reference |
|--------|--------------------|
| USGS Earthquake | [FDSN Event Web Service](https://earthquake.usgs.gov/fdsnws/event/1/) · [ComCat field definitions](https://earthquake.usgs.gov/data/comcat/) · [Magnitude types](https://www.usgs.gov/programs/earthquake-hazards/magnitude-types) · [Contributor codes](https://earthquake.usgs.gov/fdsnws/event/1/contributors) |
| GDACS | [EQ alert model](https://www.gdacs.org/knowledge/models_eq.aspx) · [API quickstart (PDF)](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v1.pdf) · [MHEWS guide (PDF)](https://www.gdacs.org/documents/2025/GDACS_MHEWS_guide.pdf) · [Feed reference](https://www.gdacs.org/feed_reference.aspx) |
| NASA EONET | [EONET v3 API docs](https://eonet.gsfc.nasa.gov/docs/v3) · [Categories](https://eonet.gsfc.nasa.gov/api/v3/categories) · [Sources](https://eonet.gsfc.nasa.gov/api/v3/sources) · [Magnitude units](https://eonet.gsfc.nasa.gov/api/v3/magnitudes) |
| Open-Meteo Flood | [Flood API docs](https://open-meteo.com/en/docs/flood-api) · [GloFAS v4 announcement](https://www.ecmwf.int/en/about/media-centre/news/2022/copernicus-emergency-management-service-releases-glofas-v40) |
| USGS NWIS | [Daily Values service](https://waterservices.usgs.gov/docs/dv-service/daily-values-service-details/) · [Parameter codes](https://help.waterdata.usgs.gov/codes-and-parameters/parameters) · [Provisional data statement](https://waterdata.usgs.gov/provisional-data-statement/) |
| Avalanche.org | [Public API docs](https://github.com/NationalAvalancheCenter/Avalanche.org-Public-API-Docs) · [North American danger scale](https://avalanche.org/avalanche-encyclopedia/human/resources/north-american-public-avalanche-danger-scale/) |
| IBTrACS | [IBTrACS product page](https://www.ncei.noaa.gov/products/international-best-track-archive) · [v04r01 column documentation (PDF)](https://www.ncei.noaa.gov/sites/default/files/2025-09/IBTrACS_v04r01_column_documentation.pdf) · [v04r01 technical details (PDF)](https://www.ncei.noaa.gov/sites/default/files/2025-04/IBTrACS_version4r01_Technical_Details.pdf) · [HURDAT2 format (PDF)](https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-atlantic.pdf) · [Dvorak technique](https://www.ospo.noaa.gov/products/ocean/tropical/dvorak.html) |
| USGS Volcano | [Volcano Alert Level system](https://www.usgs.gov/programs/VHP/alert-level-system) · [Alert level icons / UNASSIGNED](https://www.usgs.gov/programs/VHP/alert-level-icons) · [HANS notices](https://volcanoes.usgs.gov/hans-public/) · [GVP volcano numbers](https://volcano.si.edu/faq/gvp_vnums.cfm) |
| NIFC | [WFIGS Interagency Perimeters service](https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0) · [NWCG Wildland Fire Event Polygon standard (PDF)](https://fs-prod-nwcg.s3.us-gov-west-1.amazonaws.com/s3fs-public/2023-08/NWCGWildlandFireEventPolygon.pdf) · [NWCG Event Kind & Category rules (PDF)](https://fire.ak.blm.gov/content/aicc/Dispatch_Operations_right/06.%20InFORM/NWCG%20Data%20Standards/NWCG%20Event%20Kind%20and%20Category%20-%20Business%20Rules.pdf) · [NWCG glossary](https://www.nwcg.gov/nwcg-glossary-of-wildland-fire-pms-205) |
