# GEO_Download

GIS Data Downloader — a Python 3.11 application for programmatically downloading geospatial data from public APIs and storing it as daily CSV files.

## Overview

GEO_Download fetches data from public geospatial APIs and saves it locally as dated CSV files. Currently supported sources:

| Source | API | Data |
|--------|-----|------|
| USGS Earthquake | [FDSN Event Query](https://earthquake.usgs.gov/fdsnws/event/1/query) | Seismic events (lat/lon, depth, magnitude, place) |
| USGS Volcano Alerts | [HANS API](https://volcanoes.usgs.gov/hans-public/api/) | Volcano notices (alert level, color code, country code, lat/lon) |

Both sources support two loading modes:

- **Historical** — bulk download from a configured start date to yesterday (initial load).
- **Incremental** — download only the days missing since the last downloaded file (catch-up runs).

The architecture is extensible: new data sources can be added by implementing a downloader class that inherits from `BaseDownloader`, without modifying the core orchestration logic.

## Features

- **Automated date management** — automatically determines historical vs incremental mode by scanning the output folder for existing files.
- **Day-by-day download** — each day's data is saved as a separate CSV, making files easy to manage and inspect.
- **Retry with backoff** — HTTP requests use exponential backoff (5 retries) with automatic retry on 429 and 5xx status codes.
- **Abstract base class** — `BaseDownloader` provides shared session setup, JSON fetching, and CSV parsing; new sources only implement `download_by_date_range()`.
- **Factory/Registry pattern** — new data sources are added via self-registering downloader classes.
- **Frozen Pydantic models** — all configuration and parameter objects are immutable.
- **Structured logging** — each run produces a timestamped log file under `logs/<SourceName>/`.
- **CLI interface** — source selection via command-line arguments.

## Tech Stack

| Component        | Technology                                  |
|------------------|---------------------------------------------|
| Language         | Python 3.11                                 |
| Data Validation  | Pydantic >= 2.0.0                           |
| HTTP Client      | requests >= 2.31.0 (with urllib3 retry)     |
| CSV Processing   | Standard library `csv` + `io.StringIO`       |
| Testing          | pytest >= 7.0.0                             |
| Environment      | Conda                                       |

## Project Structure

```
GEO_Download/
├── run_download.py            # Entry point — CLI parsing, orchestration, CSV saving
├── config.json                # Data source configuration
├── downloader_factory.py      # Factory/registry for downloader classes
├── util.py                    # Logger setup, date range generator, file date detection
├── environment.yml            # Conda environment definition
├── model/                     # Pydantic models and enums
│   ├── __init__.py
│   ├── config.py              # AppConfig — loads config.json
│   ├── source_config.py       # SourceConfig — per-source settings
│   ├── download_params.py     # DownloadParams — download parameters
│   ├── load_params.py         # LoadParams — determines load type and date range
│   ├── e_source_type.py       # ESourceType enum (usgs_earthquake, usgs_volcano_alerts)
│   └── e_load_type.py         # ELoadType enum (HISTORICAL / INCREMENTAL)
├── downloader/                # Downloader classes (base + concrete implementations)
│   ├── __init__.py            # Imports + factory registrations
│   ├── base.py                # BaseDownloader — abstract base class
│   ├── usgs_earthquake.py     # USGSEarthquakeDownloader
│   └── usgs_volcano.py        # USGSVolcanoDownloader
├── test/                      # Unit tests
│   ├── test_base_downloader.py
│   ├── test_models.py
│   ├── test_downloader_factory.py
│   ├── test_util.py
│   ├── test_usgs_downloader.py
│   └── test_usgs_volcano_downloader.py
├── data/                      # Downloaded CSV files (per source subfolder)
│   ├── USGS_Earthquake/
│   └── USGS_Volcano_Alerts/
└── logs/                      # Timestamped log files (per source subfolder)
    ├── USGS_Earthquake/
    └── USGS_Volcano_Alerts/
```

## Configuration

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
      "output_file_pattern": "earthquakes_{date}.csv",
      "is_date_to_previous_day": true
    },
    "USGS_Volcano_Alerts": {
      "type": "usgs_volcano_alerts",
      "enabled": true,
      "api_url": "https://volcanoes.usgs.gov/hans-public/api/notice/getRecentNotices",
      "start_date": "2026-09-01",
      "output_folder": "data/USGS_Volcano_Alerts",
      "output_file_pattern": "volcano_alerts_{date}.csv",
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

## Usage

### Setup

```bash
conda env create -f environment.yml
conda activate geo_download_311
```

### Run

```bash
python run_download.py <source_name>
```

Where `<source_name>` matches a key in `config.json` (e.g. `USGS_Earthquake`, `USGS_Volcano_Alerts`).

Only enabled sources are accepted as valid arguments. The application will:

1. Load configuration from `config.json`.
2. Determine whether to run in historical or incremental mode by checking existing files in the output folder.
3. Download data for each day in the date range.
4. Save each day's data to a separate CSV file.

### Examples

**Earthquake data:**

```bash
python run_download.py USGS_Earthquake
```

```
---- USGS_Earthquake Downloader ----

Source name: USGS_Earthquake
Source type: usgs_earthquake
API URL: https://earthquake.usgs.gov/fdsnws/event/1/query
Output folder: data/USGS_Earthquake
Output file pattern: earthquakes_{date}.csv
Load type: INCREMENTAL
Start date: 2026-09-14 00:00:00
End date: 2026-09-13 00:00:00

Downloading data for 2026-09-14.
File data/USGS_Earthquake/earthquakes_2026-09-14.csv saved. Records: 142.

Done.
```

**Volcano alert data:**

```bash
python run_download.py USGS_Volcano_Alerts
```

```
---- USGS_Volcano_Alerts Downloader ----

Source name: USGS_Volcano_Alerts
Source type: usgs_volcano_alerts
API URL: https://volcanoes.usgs.gov/hans-public/api/notice/getRecentNotices
Output folder: data/USGS_Volcano_Alerts
Output file pattern: volcano_alerts_{date}.csv
Load type: HISTORICAL
Start date: 2026-09-01 00:00:00
End date: 2026-09-14 00:00:00

Downloading data for 2026-09-01.
File data/USGS_Volcano_Alerts/volcano_alerts_2026-09-01.csv saved. Records: 6.
...

Done.
```

## Data Output

Downloaded files are saved as CSV with one file per day, named by date.

### USGS Earthquake

- **Location:** `data/USGS_Earthquake/earthquakes_YYYY-MM-DD.csv`
- **Columns:** 23 fields including `time`, `latitude`, `longitude`, `depth`, `mag`, `magType`, `place`, `type`, `status`, and more.

### USGS Volcano Alerts

- **Location:** `data/USGS_Volcano_Alerts/volcano_alerts_YYYY-MM-DD.csv`
- **Columns:** 22 fields including `country_code`, `volcano_code`, `volcano_name`, `latitude`, `longitude`, `region`, `alert_level`, `color_code`, `notice_summary`, and more.

## Testing

```bash
pytest test/
```

Tests cover:
- **Base downloader** — ABC instantiation guard, session creation with retry, `_get_json()` success/error.
- **Model validation** — `SourceConfig`, `AppConfig`, `LoadParams` (historical vs incremental logic, `is_date_to_previous_day` flag).
- **Factory pattern** — registration, creation, overwrite, error cases.
- **Utilities** — `date_range()` generator, `get_recent_file_date()` file scanning.
- **Earthquake downloader** — mocked HTTP for success, empty, HTTP error, connection error, URL construction.
- **Volcano downloader** — volcano cache loading, name-to-code resolution, date parsing, record building, download with notice sections, fallback to name matching, no-data handling.

## Dataflow

```mermaid
flowchart TD
    A[config.json] -->|load| B[AppConfig]
    B -->|source lookup| C[SourceConfig]
    C -->|from_source| D[LoadParams]
    D -->|scan output folder| E{Existing files?}
    E -->|No| F[HISTORICAL mode<br/>start_date to yesterday]
    E -->|Yes| G[INCREMENTAL mode<br/>last_file_date + 1 to yesterday]
    F --> H[run_download.py]
    G --> H
    H -->|day-by-day loop| I[date_range generator]
    I --> J[DownloaderFactory.create]
    J --> K{Source type?}
    K -->|usgs_earthquake| L[USGSEarthquakeDownloader]
    K -->|usgs_volcano_alerts| M[USGSVolcanoDownloader]
    L -->|HTTP GET with retry| N[USGS FDSN API]
    M -->|HTTP GET with retry| O[USGS HANS API]
    N -->|CSV response| P[Parse CSV to list of dicts]
    O -->|JSON response + cache| Q[Build enriched records]
    P -->|per day| R[Save to data/USGS_Earthquake/]
    Q -->|per day| S[Save to data/USGS_Volcano_Alerts/]
    H -->|logging| T[logs/SourceName/download_*.log]
```

## Extensibility

To add a new data source:

1. **Add a value to `ESourceType`** in `model/e_source_type.py`.
2. **Create a downloader class** in `downloader/` (e.g. `downloader/new_source.py`) inheriting from `BaseDownloader` and implementing `download_by_date_range()`.
3. **Register the downloader** in `downloader/__init__.py` via `DownloaderFactory.register()`.
4. **Add a source entry** to `config.json` with the new type.

The base class provides shared infrastructure (session with retry, `_get_json()`, `_download_csv()`), so new sources only need to implement the date-range download logic.
