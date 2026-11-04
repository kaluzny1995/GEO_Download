← [README](../README.md)

# Configuration Reference

The application is configured via `config.json`. Each data source is defined under the `sources` key:

```json
{
  "sources": {
    "USGS_Earthquake": {
      "type": "usgs_earthquake",
      "enabled": true,
      "api_url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
      "feed_url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.csv",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_Earthquake",
      "output_file_pattern": "usgs_earthquakes_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {}
    },
    "GDACS": {
      "type": "gdacs",
      "enabled": true,
      "api_url": "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/SEARCH",
      "start_date": "2026-09-01",
      "output_folder": "data/GDACS",
      "output_file_pattern": "gdacs_disasters_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "event_types": "EQ;TC;FL;VO;WF;DR",
        "page_size": 100
      }
    },
    "EONET": {
      "type": "eonet",
      "enabled": true,
      "api_url": "https://eonet.gsfc.nasa.gov/api/v3/events",
      "start_date": "2026-09-01",
      "output_folder": "data/EONET",
      "output_file_pattern": "eonet_events_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {}
    },
    "OpenMeteo_Flood": {
      "type": "openmeteo_flood",
      "enabled": true,
      "api_url": "https://flood-api.open-meteo.com/v1/flood",
      "start_date": "2026-09-01",
      "output_folder": "data/OpenMeteo_Flood",
      "output_file_pattern": "openmeteo_rivers_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "rivers_file": "data/rivers.json",
        "thresholds_file": "data/openmeteo_discharge_thresholds.csv"
      }
    },
    "USGS_NWIS": {
      "type": "usgs_nwis",
      "enabled": true,
      "api_url": "https://waterservices.usgs.gov/nwis/iv/",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_NWIS",
      "output_file_pattern": "usgs_streamflow_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "sites": "01646500",
        "parameter_code": "00060",
        "stage_parameter_code": "00065",
        "nwps_api_url": "https://api.water.noaa.gov/nwps/v1/gauges",
        "flood_categories_file": "data/usgs_flood_categories.csv"
      }
    },
    "Avalanche_ORG": {
      "type": "avalanche_org",
      "enabled": true,
      "api_url": "https://api.avalanche.org/v2/public/products/map-layer",
      "start_date": "2026-09-01",
      "output_folder": "data/Avalanche_ORG",
      "output_file_pattern": "avalancheorg_avalanche_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "notices_file": "data/avalanche_org_notices.csv"
      }
    },
    "IBTrACS": {
      "type": "ibtracs",
      "enabled": true,
      "api_url": "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv",
      "start_date": "2026-09-01",
      "output_folder": "data/IBTrACS",
      "output_file_pattern": "ibtracs_cyclones_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "dataset": "last3years",
        "download_timeout": 300
      }
    },
    "USGS_Volcano": {
      "type": "usgs_volcano",
      "enabled": true,
      "api_url": "https://volcanoes.usgs.gov/hans-public/api/volcano",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_Volcano",
      "output_file_pattern": "usgs_volcanoes_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "notices_file": "data/usgs_volcano_notices.csv",
        "ncei_eruptions_file": "data/usgs_volcano_ncei_eruptions.csv",
        "ncei_api_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes"
      }
    },
    "NIFC": {
      "type": "nifc",
      "enabled": true,
      "api_url": "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query",
      "start_date": "2026-09-01",
      "output_folder": "data/NIFC",
      "output_file_pattern": "nifc_fires_{date}.csv",
      "is_date_to_previous_day": true,
      "params": {
        "unit_names_file": "data/nifc_unit_names.csv"
      }
    }
  }
}
```

| Field                    | Description                                                             |
|--------------------------|-------------------------------------------------------------------------|
| `type`                   | Source type identifier — maps to a registered downloader via `ESourceType` enum. |
| `enabled`                | Whether this source is active and available for download.               |
| `api_url`                | Base API URL used by the downloader to construct query requests.        |
| `feed_url`               | Optional second upstream feed URL — `str`, defaults to `""` when the key is omitted. Only `USGS_Earthquake` sets it (the rolling all-day summary feed); no downloader consumes it yet. |
| `start_date`             | Earliest date to download from (used in historical mode).               |
| `output_folder`          | Directory where CSV files are saved.                                    |
| `output_file_pattern`    | Filename pattern — `{date}` is replaced with `YYYY-MM-DD`.              |
| `is_date_to_previous_day`| If `true`, the end date is yesterday; if `false`, it's today.           |
| `params`                 | Extra keyword arguments spread into the downloader constructor (`run_download.py` calls `get_downloader(source.type, logger=logger, **source.params)`) — see [Per-source `params`](#per-source-params). |

## Per-source `params`

Every downloader accepts the shared keys below; source-specific keys are listed after them.
Unknown keys raise `TypeError` when the downloader is constructed (the chain aborts before any download).

| Key | Type / default | Meaning |
|-----|----------------|---------|
| `timeout` | `int` — `30`, or `60` for `IBTrACS` and `USGS_NWIS` | HTTP request timeout in seconds. |
| `log_folder` | `str` — unset | When set, logs go to `logs/<log_folder>/<log_folder>_<timestamp>.log` instead of `logs/downloader_<timestamp>.log`. Ignored by `run_download.py`, which always passes its own `logger`. |
| `reverse_geocode_file` | `str` — `data/reverse_geocode.csv` | Reverse-geocoding lookup file (all sources **except** `Avalanche_ORG`, whose constructor does not take it). |

| Source | Key | Type / default | Meaning |
|--------|-----|----------------|---------|
| `GDACS` | `event_types` | `str` — `EQ;TC;FL;VO;WF;DR` | `;`-separated GDACS event codes to fetch. |
| `GDACS` | `page_size` | `int` — `100` | Events per API page (the downloader pages until exhausted). |
| `OpenMeteo_Flood` | `rivers_file` | `str` — `data/rivers.json` | Rivers reference file used to build the query. |
| `OpenMeteo_Flood` | `thresholds_file` | `str` — `data/openmeteo_discharge_thresholds.csv` | Discharge threshold reference GEO_ETL joins; the download builds it when missing, `run_openmeteo_thresholds.py` refreshes it. |
| `USGS_NWIS` | `sites` | `str` — `01646500` | Gauge site ID(s) sent as the `sites=` query parameter. |
| `USGS_NWIS` | `parameter_code` | `str` — `00060` | Discharge parameter(s) sent as `parameterCd=` (`00060` = discharge, cfs); one row per gauge and day per code. |
| `USGS_NWIS` | `stage_parameter_code` | `str` — `00065` | Gauge-height parameter (`00065`, ft) requested with the discharge and aggregated into `gauge_height`; empty disables the stage column. |
| `USGS_NWIS` | `nwps_api_url` | `str` — `https://api.water.noaa.gov/nwps/v1/gauges` | NWS gauge endpoint the flood-category thresholds are read from, one request per gauge. |
| `USGS_NWIS` | `flood_categories_file` | `str` — `data/usgs_flood_categories.csv` | NWS flood-stage reference GEO_ETL joins; the download adds a gauge missing from it and leaves a covered gauge alone. |
| `IBTrACS` | `dataset` | `str` — `last3years` | IBTrACS dataset slice to download. |
| `IBTrACS` | `download_timeout` | `int` — `300` | Wall-clock budget in seconds for one full-file transfer attempt. A stalled/slow stream is aborted at this limit and retried (three bounded attempts); progress is logged every 2 MiB. |
| `Avalanche_ORG` | `notices_file` | `str` — `data/avalanche_org_notices.csv` | Local notices CSV stamped onto the downloaded rows. |
| `USGS_Volcano` | `notices_file` | `str` — `data/usgs_volcano_notices.csv` | Local notices CSV stamped onto the downloaded rows. |
| `USGS_Volcano` | `ncei_eruptions_file` | `str` — `data/usgs_volcano_ncei_eruptions.csv` | NCEI Significant Volcanic Eruptions reference stamped into `vei`, `casualties` and `damage`; the download builds it when missing. |
| `USGS_Volcano` | `ncei_api_url` | `str` — `https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes` | NCEI HazEL endpoint the eruption reference is fetched from. |
| `NIFC` | `unit_names_file` | `str` — `data/nifc_unit_names.csv` | Fire-unit name lookup CSV. |

`USGS_Earthquake` and `EONET` have no source-specific keys (`"params": {}` in the shipped config).
