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
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_Earthquake",
      "output_file_pattern": "usgs_earthquakes_{date}.csv",
      "is_date_to_previous_day": true
    },
    "GDACS": {
      "type": "gdacs",
      "enabled": true,
      "api_url": "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/SEARCH",
      "start_date": "2026-09-01",
      "output_folder": "data/GDACS",
      "output_file_pattern": "gdacs_disasters_{date}.csv",
      "is_date_to_previous_day": true
    },
    "EONET": {
      "type": "eonet",
      "enabled": true,
      "api_url": "https://eonet.gsfc.nasa.gov/api/v3/events",
      "start_date": "2026-09-01",
      "output_folder": "data/EONET",
      "output_file_pattern": "eonet_events_{date}.csv",
      "is_date_to_previous_day": true
    },
    "OpenMeteo_Flood": {
      "type": "openmeteo_flood",
      "enabled": true,
      "api_url": "https://flood-api.open-meteo.com/v1/flood",
      "start_date": "2026-09-01",
      "output_folder": "data/OpenMeteo_Flood",
      "output_file_pattern": "openmeteo_rivers_{date}.csv",
      "is_date_to_previous_day": true
    },
    "USGS_NWIS": {
      "type": "usgs_nwis",
      "enabled": true,
      "api_url": "https://waterservices.usgs.gov/nwis/dv/",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_NWIS",
      "output_file_pattern": "usgs_streamflow_{date}.csv",
      "is_date_to_previous_day": true
    },
    "IBTrACS": {
      "type": "ibtracs",
      "enabled": true,
      "api_url": "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv",
      "start_date": "2026-09-01",
      "output_folder": "data/IBTrACS",
      "output_file_pattern": "ibtracs_cyclones_{date}.csv",
      "is_date_to_previous_day": true
    },
    "USGS_Volcano": {
      "type": "usgs_volcano",
      "enabled": true,
      "api_url": "https://volcanoes.usgs.gov/hans-public/api/volcano",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_Volcano",
      "output_file_pattern": "usgs_volcanoes_{date}.csv",
      "is_date_to_previous_day": true
    },
    "NIFC": {
      "type": "nifc",
      "enabled": true,
      "api_url": "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query",
      "start_date": "2026-09-01",
      "output_folder": "data/NIFC",
      "output_file_pattern": "nifc_fires_{date}.csv",
      "is_date_to_previous_day": true
    }
  }
}
```

| Field                    | Description                                                             |
|--------------------------|-------------------------------------------------------------------------|
| `type`                   | Source type identifier — maps to a registered downloader via `ESourceType` enum. |
| `enabled`                | Whether this source is active and available for download.               |
| `api_url`                | Base API URL used by the downloader to construct query requests.        |
| `start_date`             | Earliest date to download from (used in historical mode).               |
| `output_folder`          | Directory where CSV files are saved.                                    |
| `output_file_pattern`    | Filename pattern — `{date}` is replaced with `YYYY-MM-DD`.              |
| `is_date_to_previous_day`| If `true`, the end date is yesterday; if `false`, it's today.           |
| `params`                 | Additional source-specific parameters passed to the downloader constructor. |
