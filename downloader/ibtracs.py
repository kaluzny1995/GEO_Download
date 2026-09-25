from __future__ import annotations

import csv
import datetime as dt
import io
import logging

import requests

from downloader.base import BaseDownloader


class IBTrACSDownloader(BaseDownloader):
    """Downloads global tropical cyclone best-track data from NOAA IBTrACS.

    IBTrACS provides the most complete global collection of tropical cyclone
    data, merging best-track data from WMO Regional Specialized Meteorological
    Centres worldwide. Data includes storm position, wind speed, pressure,
    and landfall information.

    Memory-optimised: streams the CSV line-by-line and filters rows during
    the stream so the full multi-hundred-MB dataset is never held in memory.
    """

    __slots__ = ("_dataset",)

    def __init__(self, timeout: int = 60, logger: logging.Logger | None = None,
                 log_folder: str | None = None,
                 dataset: str = "last3years"):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._dataset = dataset

    def _build_url(self, base_url: str) -> str:
        """Build the download URL for the IBTrACS dataset."""
        return f"{base_url}/ibtracs.{self._dataset}.list.v04r01.csv"

    def download_by_date_range(self, base_url: str, start_date: dt.datetime,
                               end_date: dt.datetime) -> list[dict]:
        """Download IBTrACS tropical cyclone data for the given date range.

        Streams the CSV response line-by-line, skipping the units row (row 2),
        and only keeps records whose ISO_TIME falls within [start_date, end_date].
        The full multi-hundred-MB dataset is never materialized in memory.
        """
        url = self._build_url(base_url)
        start_str = self._format_date(start_date)
        end_str = self._format_date(end_date)

        self.logger.info(f"Downloading IBTrACS data from: {url}")
        self.logger.info(f"Filtering for period: {start_str} to {end_str}")

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch IBTrACS: {e}")
            return []

        try:
            filtered: list[dict] = []
            header: list[str] | None = None
            row_count = 0
            kept_count = 0

            for raw_line in response.iter_lines():
                line = raw_line.decode("utf-8", errors="replace")
                row_count += 1

                # Row 1: header
                if header is None:
                    header = line.split(",")
                    continue

                # Row 2: units — skip
                if row_count == 2:
                    continue

                # Parse ISO_TIME from the raw line to avoid materializing a dict.
                # Header: SEASON,BASIN,SUBBASIN,ISO_TIME,...
                # ISO_TIME is column index 3 in IBTrACS v04r01.
                try:
                    fields = next(csv.reader(io.StringIO(line)))
                    iso_time = fields[3].strip() if len(fields) > 3 else ""
                except (StopIteration, IndexError):
                    continue

                if not iso_time:
                    continue

                record_date = iso_time[:10]
                if start_str <= record_date < end_str:
                    # Only now build the full dict
                    row_dict = dict(zip(header, fields, strict=False))
                    filtered.append(row_dict)
                    kept_count += 1

            self.logger.info(f"Scanned {row_count} rows, kept {kept_count} records for the date range")
            return filtered
        finally:
            response.close()
