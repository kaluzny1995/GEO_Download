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
| **No data** | If a source returns nothing for a day, no file is written for that day. |

## USGS Earthquake

- **File:** `data/USGS_Earthquake/usgs_earthquakes_YYYY-MM-DD.csv` · 23 columns
- **Grain:** one row per seismic event · **Provenance:** passed through unchanged from the USGS FDSN Event Query (`format=csv`), so column names/order are USGS's own.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `time` | ISO-8601 UTC | Origin time of the event, e.g. `2026-09-01T23:58:46.050Z` |
| `latitude` | degrees | Epicentre latitude |
| `longitude` | degrees | Epicentre longitude |
| `depth` | km | Hypocentral depth |
| `mag` | magnitude | Magnitude value |
| `magType` | code | Magnitude scale: `ml`, `md`, `mb`, `mww`, `mwr`, `mw`, `ci`, … |
| `nst` | count | Number of seismic stations that reported arrivals |
| `gap` | degrees | Azimuthal gap — largest azimuth sector with no reporting station |
| `dmin` | degrees | Distance to the nearest reporting station |
| `rms` | seconds | Root-mean-square travel-time residual |
| `net` | code | Network that contributed the origin solution (`ci`, `us`, `ak`, …) |
| `id` | string | Event ID (e.g. `ci41540448`) — unique, used as `eventid` by USGS |
| `updated` | ISO-8601 UTC | Time the record was last revised |
| `place` | text | Human-readable location, e.g. `9 km WSW of Idyllwild, CA` |
| `type` | code | Event type: normally `earthquake`, also `explosion`, `quarry blast`, … |
| `horizontalError` | km | Horizontal (epicentre) location error |
| `depthError` | km | Depth location error |
| `magError` | magnitude units | Magnitude error |
| `magNst` | count | Number of stations used to compute the magnitude |
| `status` | code | `reviewed` (analyst checked) or `automatic` |
| `locationSource` | code | Network that supplied the epicentre |
| `magSource` | code | Network that supplied the magnitude |

## GDACS (Global Disasters)

- **File:** `data/GDACS/gdacs_disasters_YYYY-MM-DD.csv` · 17 columns
- **Grain:** one row per disaster event/episode · **Provenance:** flattened from the GDACS GeoJSON `features[].properties` + `geometry`.
- **Event types:** `EQ` earthquake, `TC` tropical cyclone, `FL` flood, `VO` volcano, `WF` wildfire, `DR` drought.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `event_type` | code | `EQ` / `TC` / `FL` / `VO` / `WF` / `DR` |
| `event_id` | string | GDACS event ID |
| `event_name` | text | Title, e.g. `Flood in Spain`, `Tropical Cyclone NORBERT-26` |
| `alert_level` | enum | Impact alert: `Red`, `Orange`, `Green` |
| `country` | text | Country name; blank for marine cyclones, may be a comma-separated list |
| `country_code` | ISO-3166 alpha-3 | e.g. `AUS`, `ESP`, `JPN` |
| `latitude` | degrees | Event centroid latitude (GeoJSON geometry) |
| `longitude` | degrees | Event centroid longitude |
| `from_date` | ISO local time (no zone) | Start of the event / impact window |
| `to_date` | ISO local time (no zone) | End of the event / impact window |
| `date_modified` | ISO local time (no zone) | Last time GDACS updated the event |
| `severity` | number | Numeric severity — meaning depends on `severity_unit` |
| `severity_text` | text | Same value as a sentence, e.g. `Green impact for forestfire in 14196 ha` |
| `severity_unit` | unit | `ha` burned area (WF) · `M` magnitude (EQ) · `km/h` max wind (TC) · `km2` affected area (DR) · empty for FL |
| `source` | code | Contributing body: `NEIC`, `NOAA`, `GWIS`, `GLOFAS`, `GDO`, … |
| `report_url` | URL | GDACS report page for the event |
| `is_current` | `true` / `false` | Whether the event is still current/ongoing |

## NASA EONET (Natural Events)

- **File:** `data/EONET/eonet_events_YYYY-MM-DD.csv` · 17 columns
- **Grain:** one row per EONET event · **Provenance:** flattened from `events[]`.
- **Categories:** `wildfires`, `severeStorms`, `floods`, `volcanoes`, `earthquakes`, `drought`, `landslides`, `seaLakeIce`, `snow`, `tempExtremes`, `dustHaze`, `manmade`, `waterColor`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `event_id` | string | EONET ID, e.g. `EONET_24483` |
| `event_name` | text | Event title, e.g. `Wildfire Breezy, Starr, Texas` |
| `category_id` | code | First category id (`wildfires`, `seaLakeIce`, …) |
| `category_name` | text | First category title (`Wildfires`, `Sea and Lake Ice`, …) |
| `description` | text | Short description, usually a location (`7 Miles NE from Rio Grande City, TX`); often blank |
| `source_id` | code | First source id (`IRWIN`, `JTWC`, `GDACS`, `NASA`, …) |
| `source_url` | URL | Link to the upstream source record |
| `latitude` | degrees | Latitude of the **first** geometry point (for polygons: first ring vertex) |
| `longitude` | degrees | Longitude of the first geometry point |
| `event_date` | ISO-8601 UTC | Timestamp of the first geometry |
| `magnitude_value` | number | Magnitude of the first geometry — meaning depends on `magnitude_unit` |
| `magnitude_unit` | unit | `acres` (burned area), `kts` (wind), `NM²` (ice area), … |
| `closed` | ISO-8601 UTC | When the source closed the event; empty while open (EONET returns open events by default, so this is normally blank) |
| `geometry_count` | count | Number of geometries (positions) attached to the event |
| `last_latitude` | degrees | Latitude of the **most recent** geometry |
| `last_longitude` | degrees | Longitude of the most recent geometry |
| `last_date` | ISO-8601 UTC | Timestamp of the most recent geometry |

## Open-Meteo Flood (River Discharge)

- **File:** `data/OpenMeteo_Flood/openmeteo_rivers_YYYY-MM-DD.csv` · 6 columns
- **Grain:** one row per river per day · **Coverage:** 126 major rivers from `data/rivers.json` (GloFAS model, 5 km); days with `null` discharge are skipped.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `river_name` | text | River name from `data/rivers.json` (`Amazon`, `Paraná`, …) |
| `country` | text | Country the reference point lies in (from `rivers.json`) |
| `latitude` | degrees | Reference-point latitude from `rivers.json` (the point queried) |
| `longitude` | degrees | Reference-point longitude from `rivers.json` |
| `date` | `YYYY-MM-DD` | Day of the discharge value |
| `discharge_m3s` | m³/s | Daily mean river discharge (e.g. `77982.05` for the Amazon) |

## USGS NWIS (US Streamflow)

- **File:** `data/USGS_NWIS/usgs_streamflow_YYYY-MM-DD.csv` · 9 columns
- **Grain:** one row per gauge per day · **Defaults:** site `01646500` (Potomac River near Washington DC), parameter `00060` (discharge) — both configurable via `sites` / `parameter_code`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `site_id` | string | `USGS-` + gauge number, e.g. `USGS-01646500` |
| `site_name` | text | Gauge name, e.g. `POTOMAC RIVER NEAR WASH, DC LITTLE FALLS PUMP STA` |
| `parameter_code` | code | USGS parameter code — `00060` = discharge, daily mean |
| `date` | `YYYY-MM-DD` | Day of the value (truncated from the API's `dateTime`) |
| `value` | number | Daily mean value for the day |
| `unit` | unit | `ft3/s` for parameter `00060` |
| `qualifiers` | flags | NWIS quality flags, comma-joined: `P` provisional (subject to revision), `A` approved, `e` estimated |
| `latitude` | degrees | Gauge latitude |
| `longitude` | degrees | Gauge longitude |

## Avalanche.org (US Avalanche Forecasts)

- **File:** `data/Avalanche_ORG/avalancheorg_avalanche_YYYY-MM-DD.csv` · 14 columns
- **Grain:** one row per forecast zone per day · **Coverage:** 28 US avalanche centers / 82+ zones; the map-layer endpoint is queried once per day.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `zone_id` | integer | Forecast-zone id (GeoJSON feature id) |
| `zone_name` | text | Zone name |
| `center_id` | code | Avalanche-center id, e.g. `BAC` |
| `center_name` | text | Full center name, e.g. `Bridgeport Avalanche Center` |
| `state` | 2-letter code | US state the zone lies in (`CA`, `CO`, …) |
| `danger_level` | `-1` … `5` | Numeric danger rating: `-1` no rating, `1` low, `2` moderate, `3` considerable, `4` high, `5` extreme |
| `danger_rating` | text | Same rating as text: `no rating`, `low`, `moderate`, `considerable`, `high`, `extreme` |
| `travel_advice` | text | Avalanche advice for the current rating, e.g. `Watch for signs of unstable snow …` |
| `off_season` | `True` / `False` | Whether the zone is out of its forecast season |
| `forecast_start` | ISO local datetime | Start of the forecast validity window (empty when unrated) |
| `forecast_end` | ISO local datetime | End of the forecast validity window |
| `warning` | text | Active warning product (`warning.product`); usually empty |
| `link` | URL | The center's public forecast page |
| `date` | `YYYY-MM-DD` | Day that was queried — added by the downloader, not present in the API response |

## IBTrACS (Global Tropical Cyclones)

- **File:** `data/IBTrACS/ibtracs_cyclones_YYYY-MM-DD.csv` · **174 columns**
- **Grain:** one row per cyclone position (best-track point) · **Provenance:** NOAA IBTrACS v04r01 (`last3years` by default), streamed row-by-row; the upstream *units* row (row 2) is discarded and only rows whose `ISO_TIME` falls inside the requested day are kept.
- `ISO_TIME` is looked up **by header name**, never by a fixed column index — the live header starts `SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,…`, so any positional assumption silently filters out every row.
- The upstream `last3years` file trails the present by 1–2 days, so the most recent days can legitimately yield no rows (and therefore no file); the next incremental run retries them.
- Missing values are blank cells (IBTrACS's own convention).

### Core columns (19)

| Column | Unit | Description |
|--------|------|-------------|
| `SID` | string | IBTrACS storm identifier (`basin + year + number …`) |
| `SEASON` | year | Year in which the storm started |
| `NUMBER` | integer | Storm number within the season |
| `BASIN` | code | First-basin code: `NA`, `EP`, `WP`, `NI`, `SI`, `SP`, `SA` (or `MM` missing) |
| `SUBBASIN` | code | Sub-basin code, e.g. `CS`, `GM`, `AS`, `WA`, `EA` |
| `NAME` | string | Storm name as reported by the agency (blank when unnamed) |
| `ISO_TIME` | UTC datetime | Position timestamp `YYYY-MM-DD HH:MM:SS`, normally 6-hourly (sometimes 3-hourly) — **the column the downloader filters on** |
| `NATURE` | code | Combined storm type: `DS` disturbance, `TS` tropical, `ET` extratropical, `SS` subtropical, `NR` not reported, `MX` mixture |
| `LAT` | deg north | Merged best-track latitude |
| `LON` | deg east | Merged best-track longitude |
| `WMO_WIND` | knots | Maximum sustained wind from the responsible WMO agency (averaging period differs: 1-min US, 3-min India, 10-min elsewhere) |
| `WMO_PRES` | mb | Minimum central pressure assigned by the WMO agency |
| `WMO_AGENCY` | code | Agency responsible for the basin, e.g. `hurdat/atcf`, `tokyo`, `newdelhi`, `reunion`, `bom`, `nadi`, `wellington` |
| `TRACK_TYPE` | code | `MAIN`, `spur`, `PROVISIONAL`, `PROVISIONAL_spur`, `US-PROVISIONAL`, `US-PROVISIONAL_spur` |
| `DIST2LAND` | km | Distance from the position to the nearest land (continents + islands > 1400 km²) |
| `LANDFALL` | km | Nearest distance to land during the *next* timestep (~3 h); `0` = landfall within 3 h |
| `IFLAG` | 15 chars | Interpolation flag, one char per source dataset: `_` missing, `O` original, `P` fully interpolated, `I` intensity interpolated, `V` partly interpolated |
| `STORM_SPEED` | knots | Translation speed computed from `LAT`/`LON` |
| `STORM_DIR` | degrees | Translation direction, degrees east of north (0–360, rounded to 5°) |

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
| `_AGENCY` | — | Agency that reported this row |
| `_ATCF_ID` | — | ATCF storm ID (e.g. `EP112026`) |
| `_LAT` | deg north | Latitude reported by this agency |
| `_LON` | deg east | Longitude reported by this agency |
| `_RECORD` | — | Record identifier: `G` genesis, `L` landfall, `I` intensity peak, `P` min pressure, `W` max wind, `S` status change, `T` track detail, `R` rapid change, `C` closest coast approach |
| `_STATUS` | — | System status: `DB`, `TD`, `TS`, `TY`, `ST`, `TC`, `HU`, `HR`, `SD`, `SS`, `EX`, `PT`, `IN`, `DS`, `LO`, `WV`, `ET`, `MD`, `XX` |
| `_WIND` | knots | Agency maximum sustained wind |
| `_PRES` | mb | Agency minimum central pressure |
| `_SSHS` | category | Saffir-Simpson category: `-5` unknown, `-4` post-tropical, `-3` disturbance, `-2` subtropical, `-1` TD, `0` TS, `1`–`5` Cat 1–5 |
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
| `_EYE` | nmile | Eye diameter |
| `_GUST` | knots | Maximum reported wind gust |
| `_SEAHGT` | ft | Wave height used with the `SEARAD` radii |
| `_SEARAD_NE` | nmile | Radial extent of those seas NE of the centre |
| `_SEARAD_SE` | nmile | Radial extent of those seas SE of the centre |
| `_SEARAD_SW` | nmile | Radial extent of those seas SW of the centre |
| `_SEARAD_NW` | nmile | Radial extent of those seas NW of the centre |
| `_GRADE` | — | Agency intensity grade (JMA grade, IMD grade) |
| `_R50_DIR` | degrees | Direction of the shortest 50 kt (25 m/s) wind radius |
| `_R50_LONG` | nmile | Longest radius of 50 kt (25 m/s) winds or greater |
| `_R50_SHORT` | nmile | Shortest radius of 50 kt (25 m/s) winds or greater |
| `_R30_DIR` | degrees | Direction of the shortest 30 kt (15 m/s) wind radius |
| `_R30_LONG` | nmile | Longest radius of 30 kt (15 m/s) winds or greater |
| `_R30_SHORT` | nmile | Shortest radius of 30 kt (15 m/s) winds or greater |
| `_LAND` | flag | Landfall / passage indicator (JMA) |
| `_CAT` | category | Agency category / intensity class |
| `_CI` | Dvorak CI# | Dvorak current-intensity number |
| `_DP` | mb | Dvorak-derived central pressure |
| `_TYPE` | — | Agency storm type / classification |
| `_TNUM` | Dvorak T# | Dvorak T-number |
| `_GUST_PER` | seconds | Gust averaging period (Australian data = 3 s) |
| `_POS_METHOD` | — | Code of the tool used to derive the centre position |
| `_PRES_METHOD` | — | Code of the pressure–wind relationship used |
| `_STAGE` | — | Agency stage / intensity code (DS824, TD9636) |
| `_CLASS` | — | Agency class: `TC` tropical, `EX` extratropical, `MM` missing |

_File total: **174 columns** = 19 core + 155 agency._

## USGS Volcano

- **File:** `data/USGS_Volcano/usgs_volcanoes_YYYY-MM-DD.csv` · 11 columns
- **Grain:** one row per notice for an elevated volcano · **Coverage:** only volcanoes above `NORMAL` alert (ADVISORY / WATCH / WARNING), filtered to notices issued inside the requested day.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `volcano_name` | text | Volcano name, e.g. `Ahyi Seamount`, `Kilauea` |
| `vnum` | integer | VNUM volcano number, e.g. `284141` |
| `observatory` | code | Observatory abbreviation: `avo`, `calvo`, `cvo`, `hvo`, `nmi`, `yvo` |
| `observatory_name` | text | Full observatory name, e.g. `Alaska Volcano Observatory` |
| `alert_level` | enum | Volcano Alert Level: `ADVISORY`, `WATCH`, `WARNING` |
| `color_code` | enum | Aviation Color Code: `YELLOW`, `ORANGE`, `RED` |
| `notice_type` | code | `DU` daily update · `WU` weekly update · `VV` volcanic activity notice |
| `notice_identifier` | string | Unique notice id, e.g. `DOI-USGS-NMI-2026-09-10T23:17:05+00:00` |
| `notice_date` | `YYYY-MM-DD HH:MM:SS` UTC | Time the notice was sent (`sent_utc`) — this is what the day filter uses |
| `notice_url` | URL | Human-readable notice page |
| `notice_data_url` | URL | HANS API endpoint returning the notice JSON/HTML |

## NIFC (US Wildland Fires)

- **File:** `data/NIFC/nifc_fires_YYYY-MM-DD.csv` · 16 columns
- **Grain:** one row per fire-perimeter feature updated inside the day · **Provenance:** ArcGIS FeatureServer `attributes` from the WFIGS *Interagency Perimeters* layer — polygon geometry is not requested, but the feature **centroid** is (`returnCentroid=true`), which supplies `latitude`/`longitude`.

| Column | Type / unit | Description |
|--------|-------------|-------------|
| `incident_name` | text | Fire / incident name (`poly_IncidentName`) |
| `irwin_id` | GUID | IRWIN incident identifier, e.g. `{C4138756-…}` |
| `fire_number` | epoch ms | **Named misleadingly** — it holds the fire discovery date/time (`attr_FireDiscoveryDateTime`) |
| `acres` | acres | GIS-calculated perimeter size (`poly_GISAcres`) |
| `percent_contained` | % | Percent of the fire contained (`attr_PercentContained`) |
| `fire_type` | code | Incident type category (`attr_IncidentTypeCategory`), e.g. `WF`, `RX`, `CX` |
| `fire_type_label` | text | Feature category (`poly_FeatureCategory`), e.g. *Wildfire Daily Fire Perimeter*, *Prescribed Fire* |
| `jurisdiction` | code | Point-of-origin jurisdictional agency (`attr_POOJurisdictionalAgency`), e.g. `USFS`, `BLM`, `NPS`, `BIA` — empty when unset |
| `jurisdiction_label` | code | Jurisdictional unit beneath that agency (`attr_POOJurisdictionalUnit`), e.g. `WAOWF`, `ORUMF` |
| `state` | 2-letter code | Point-of-origin state (`attr_POOState`) with the `US-` prefix stripped |
| `po_method` | code | Point-of-origin state as stored by IRWIN (`attr_POOState`), e.g. `US-CO` |
| `latitude` | degrees | Perimeter centroid latitude (falls back to `attr_InitialLatitude`) |
| `longitude` | degrees | Perimeter centroid longitude (falls back to `attr_InitialLongitude`) |
| `poly_date` | epoch ms | When the perimeter was last current (`poly_DateCurrent`) |
| `created_on` | epoch ms | Record creation time (`attr_CreatedOnDateTime_dt`) |
| `modified_on` | epoch ms | Record modification time (`attr_ModifiedOnDateTime_dt`) |

> ℹ **Layer-specific field names.** On the *Perimeters* layer `poly_*` are perimeter
> attributes and `attr_*` are incident attributes mirrored onto each perimeter — every
> name in the request must exist in that schema. ArcGIS rejects an unknown `outFields`
> list with **HTTP 200** plus `{"error":{"code":400,…,"details":["'outFields' parameter is invalid"]}}`,
> which reads as "0 records" rather than as a failure. This source silently produced no
> files from 2026-09-18 until 2026-09-26, when the columns were re-mapped to real field
> names and the downloader started logging `error` payloads (`NIFC API rejected the query: …`).
> The layer exposes no human-readable agency name, hence `jurisdiction_label` holds a unit *code*.
>
> Fields a query must not omit: `poly_IncidentName`, `poly_IRWINID`, `poly_FeatureCategory`,
> `poly_GISAcres`, `poly_DateCurrent`, `attr_IncidentTypeCategory`, `attr_FireDiscoveryDateTime`,
> `attr_PercentContained`, `attr_POOJurisdictionalAgency`, `attr_POOJurisdictionalUnit`,
> `attr_POOState`, `attr_InitialLatitude`, `attr_InitialLongitude`,
> `attr_CreatedOnDateTime_dt`, `attr_ModifiedOnDateTime_dt` — kept in
> `NIFCDownloader._OUT_FIELDS` (downloader/nifc.py).
