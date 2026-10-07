← [README](../README.md)

# Architecture & Project Layout

## Project Structure

```
GEO_Download/
├── run_download.py            # Entry point — CLI parsing, orchestration, CSV saving, exit codes
├── run_openmeteo_thresholds.py # GloFAS baseline percentiles → data/openmeteo_discharge_thresholds.csv (threshold reference for GEO_ETL; run_download builds it when missing)
├── config.json                # Data source configuration
├── downloader_factory.py      # Factory/registry for downloader classes
├── util.py                    # Logger setup, date range generator, file date detection
├── reverse_geocode.py         # Reverse geocoding — shared geocode_country/geocode_state lookup (used by downloader/base.py)
├── environment.yml            # Conda environment definition
├── pyproject.toml             # Ruff rules + pytest config
├── tox.ini                    # lint / test / typecheck / format environments
├── model/                     # Pydantic models and enums
│   ├── __init__.py
│   ├── config.py              # AppConfig — loads config.json
│   ├── source_config.py       # SourceConfig — per-source settings
│   ├── download_params.py     # DownloadParams — download parameters
│   ├── load_params.py         # LoadParams — determines load type and date range
│   ├── e_source_type.py       # ESourceType enum (usgs_earthquake, gdacs, eonet, openmeteo_flood, usgs_nwis, avalanche_org, ibtracs, usgs_volcano, nifc)
│   └── e_load_type.py         # ELoadType enum (HISTORICAL / INCREMENTAL)
├── downloader/                # Downloader classes (base + concrete implementations)
│   ├── __init__.py            # Imports + factory registrations
│   ├── base.py                # BaseDownloader — abstract base class
│   ├── usgs_earthquake.py     # USGSEarthquakeDownloader
│   ├── gdacs.py               # GDACSDownloader
│   ├── eonet.py               # EONETDownloader
│   ├── openmeteo_flood.py     # OpenMeteoFloodDownloader
│   ├── usgs_nwis.py           # USGSNWISDownloader
│   ├── avalanche_org.py       # AvalancheOrgDownloader
│   ├── ibtracs.py             # IBTrACSDownloader
│   ├── usgs_volcano.py       # USGSVolcanoDownloader
│   ├── nifc.py                # NIFCDownloader
├── test/                      # Unit tests (test/ root + test/downloader/ subpackage)
│   ├── __init__.py
│   ├── test_downloader_factory.py
│   ├── test_models.py
│   ├── test_openmeteo_thresholds.py
│   ├── test_reverse_geocode.py
│   ├── test_run_download.py
│   ├── test_util.py
│   └── downloader/            # Per-downloader tests (a pytest subpackage)
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_avalanche_org_downloader.py
│       ├── test_base_downloader.py
│       ├── test_eonet_downloader.py
│       ├── test_gdacs_downloader.py
│       ├── test_ibtracs_downloader.py
│       ├── test_nifc_downloader.py
│       ├── test_openmeteo_flood_downloader.py
│       ├── test_usgs_downloader.py
│       ├── test_usgs_nwis_downloader.py
│       └── test_usgs_volcano_downloader.py
├── data/                      # Downloaded CSV files (per source subfolder)
│   ├── USGS_Earthquake/
│   ├── GDACS/
│   ├── EONET/
│   ├── OpenMeteo_Flood/
│   ├── USGS_NWIS/
│   ├── Avalanche_ORG/
│   ├── IBTrACS/
│   ├── USGS_Volcano/
│   ├── NIFC/
│   ├── openmeteo_discharge_thresholds.csv  # Per-river GloFAS baseline percentiles (p50/p90/p95/p99) — created by run_download.py when missing, refreshed by run_openmeteo_thresholds.py
│   ├── usgs_flood_categories.csv  # NWS flood stage thresholds per gauge (action/minor/moderate/major) — kept present by run_download.py
│   ├── rivers.json            # River definitions (126 major world rivers)
│   ├── avalanche_org_notices.csv  # Avalanche zone centroid lookup (place_location, state, latitude, longitude)
│   ├── nifc_unit_names.csv    # NIFC jurisdiction unit lookup (unit_code, unit_name)
│   ├── reverse_geocode.csv    # Reverse geocode lookup stamped into the source CSVs at download time (latitude, longitude, country_code, state_province)
│   └── usgs_volcano_notices.csv  # USGS volcano notice lookup (notice_identifier, vnum, notice_type, latitude, longitude, region, synopsis)
└── logs/                      # Timestamped log files (per source subfolder)
    ├── USGS_Earthquake/
    ├── GDACS/
    ├── EONET/
    ├── OpenMeteo_Flood/
    ├── USGS_NWIS/
    ├── Avalanche_ORG/
    ├── IBTrACS/
    ├── USGS_Volcano/
    ├── NIFC/
```

## Extensibility

To add a new data source:

1. **Add a value to `ESourceType`** in `model/e_source_type.py`.
2. **Create a downloader class** in `downloader/` (e.g. `downloader/new_source.py`) inheriting from `BaseDownloader` and implementing `download_by_date_range()`.
3. **Register the downloader** in `downloader/__init__.py` via `DownloaderFactory.register()`.
4. **Add a source entry** to `config.json` with the new type.

The base class provides shared infrastructure (session with retry, `_get_json()`, `_download_csv()`), so new sources only need to implement the date-range download logic.

## Exit codes

`run_download.py` ends with `sys.exit(main())`. `main()` returns `0` on success; when there is nothing to ingest, `download_source()` **raises `RuntimeError`**, which ends the process with a traceback on stderr and exit code `1` — the code a chained pipeline reacts to:

| Code | Situation | Logged as |
|------|-----------|-----------|
| `0` | At least one CSV was written | `File … saved. Records: N.` → `Done.` |
| `0` | Nothing to download — the newest local file is already past the end date (`date_from > date_to`) | `Recent file date is bigger than end date. Nothing to download.` |
| `1` | The run covered a date range but **no file was written** — every day empty (upstream feed has no data yet / API error payload), or every write failed → `RuntimeError` raised | `ERROR No files downloaded for <Source> in <from>..<to> — nothing to ingest.` + traceback |
| `2` | CLI usage error (unknown or disabled source) — argparse | usage message |
| `1` | Any other unhandled exception in a downloader | traceback |

After the CSVs are written (and only then) `download_source()` calls the downloader's `ensure_auxiliary_files()` hook — a no-op in `BaseDownloader`, overridden by `OpenMeteo_Flood` to build `data/openmeteo_discharge_thresholds.csv` when it is missing and by `USGS_NWIS` to add any configured gauge missing from `data/usgs_flood_categories.csv`, so GEO_ETL's `danger_rating` / `other_metrics` are filled from the first run. It is deliberately best effort: a failure there is logged as `ERROR Auxiliary files of <Source> … could not be created` and the run still exits `0`, because the day's data is already on disk; the next run then tries again.

In GEO_E2E a non-zero code is handled by the two `jobs.json` flags of that job — `is_failed_if_error: true` logs `ERROR DOWNLOAD job for "<source>" exited with return code 1` and raises (Celery task FAILURE); the shipped value is `is_failed_if_error: false` + `is_stop_if_error: true`, which only logs `WARNING … — next jobs will not be executed` and keeps the task SUCCESS. Either way `INGESTION` / `DATA_QUALITY` never start. That is what keeps a stale upstream feed (e.g. IBTrACS, whose `last3years` file updates with a delay) from triggering an ingestion of files that did not change.
