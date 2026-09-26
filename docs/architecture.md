← [README](../README.md)

# Architecture & Project Layout

## Project Structure

```
GEO_Download/
├── run_download.py            # Entry point — CLI parsing, orchestration, CSV saving
├── config.json                # Data source configuration
├── downloader_factory.py      # Factory/registry for downloader classes
├── util.py                    # Logger setup, date range generator, file date detection
├── environment.yml            # Conda environment definition
├── pyproject.toml             # Ruff rules + pytest config
├── tox.ini                    # lint / test / typecheck / format environments
├── model/                     # Pydantic models and enums
│   ├── __init__.py
│   ├── config.py              # AppConfig — loads config.json
│   ├── source_config.py       # SourceConfig — per-source settings
│   ├── download_params.py     # DownloadParams — download parameters
│   ├── load_params.py         # LoadParams — determines load type and date range
│   └── e_source_type.py       # ESourceType enum (usgs_earthquake, gdacs, eonet, openmeteo_flood, usgs_nwis, avalanche_org, ibtracs, usgs_volcano, nifc)
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
├── test/                      # Unit tests
│   ├── test_base_downloader.py
│   ├── test_models.py
│   ├── test_downloader_factory.py
│   ├── test_util.py
│   ├── test_usgs_downloader.py
│   ├── test_gdacs_downloader.py
│   ├── test_eonet_downloader.py
│   ├── test_openmeteo_flood_downloader.py
│   ├── test_usgs_nwis_downloader.py
│   ├── test_ibtracs_downloader.py
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
│   └── rivers.json            # River definitions (126 major world rivers)
└── logs/                      # Timestamped log files (per source subfolder)
    ├── USGS_Earthquake/
    ├── GDACS/
    ├── EONET/
    ├── OpenMeteo_Flood/
    ├── USGS_NWIS/
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
