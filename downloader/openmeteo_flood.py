from __future__ import annotations
import logging
import datetime as dt
import json
from pathlib import Path

from downloader.base import BaseDownloader


class OpenMeteoFloodDownloader(BaseDownloader):
    """Downloads river discharge data from the Open-Meteo Flood API (GloFAS).

    Queries daily river discharge (m3/s) for a list of major world rivers
    defined in data/rivers.json.
    """

    DEFAULT_RIVERS_FILE = str(Path(__file__).resolve().parent.parent / "data" / "rivers.json")

    def __init__(self, timeout: int = 30, logger: logging.Logger | None = None,
                 log_folder: str | None = None,
                 rivers_file: str | None = None):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._rivers_file = rivers_file or self.DEFAULT_RIVERS_FILE
        self._rivers = self._load_rivers()

    def _load_rivers(self) -> list[dict]:
        """Load river definitions from JSON file."""
        with open(self._rivers_file, "r") as f:
            return json.load(f)

    def _query_river(self, base_url: str, river: dict, start_date: dt.datetime, end_date: dt.datetime) -> dict | None:
        """Query Open-Meteo Flood API for a single river."""
        url = (
            f"{base_url}"
            f"?latitude={river['latitude']}"
            f"&longitude={river['longitude']}"
            f"&daily=river_discharge"
            f"&start_date={self._format_date(start_date)}"
            f"&end_date={self._format_date(end_date)}"
        )
        result = self._get_json(url)
        return result if isinstance(result, dict) else None

    def _build_records(self, river: dict, data: dict, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Build flat records from API response for one river."""
        daily = data.get("daily", {})
        times = daily.get("time", [])
        discharges = daily.get("river_discharge", [])

        records = []
        for date_str, discharge in zip(times, discharges):
            if discharge is None:
                continue
            records.append({
                "river_name": river["name"],
                "country": river["country"],
                "latitude": river["latitude"],
                "longitude": river["longitude"],
                "date": date_str,
                "discharge_m3s": discharge,
            })
        return records

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download river discharge data for all rivers in the date range.

        Queries each river individually and aggregates results.
        """
        self.logger.info(f"Downloading Open-Meteo Flood data for {start_date.date()} to {end_date.date()}")
        self.logger.info(f"Monitoring {len(self._rivers)} rivers")

        all_records: list[dict] = []
        rivers_with_data = 0

        for i, river in enumerate(self._rivers, 1):
            data = self._query_river(base_url, river, start_date, end_date)
            if data and isinstance(data, dict):
                records = self._build_records(river, data, start_date, end_date)
                if records:
                    all_records.extend(records)
                    rivers_with_data += 1

            if i % 20 == 0:
                self.logger.info(f"  Progress: {i}/{len(self._rivers)} rivers queried")

        self.logger.info(f"Downloaded {len(all_records)} discharge records from {rivers_with_data}/{len(self._rivers)} rivers")
        return all_records
