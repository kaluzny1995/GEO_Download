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

    ISO_TIME_COLUMN = "ISO_TIME"

    __slots__ = ("_dataset",)

    def __init__(self, timeout: int = 60, logger: logging.Logger | None = None,
                 log_folder: str | None = None,
                 dataset: str = "last3years"):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._dataset = dataset

    def _build_url(self, base_url: str) -> str:
        """Build the download URL for the IBTrACS dataset."""
        return f"{base_url}/ibtracs.{self._dataset}.list.v04r01.csv"

    @staticmethod
    def _parse_line(line: str) -> list[str]:
        """Parse a single CSV line into fields."""
        try:
            return next(csv.reader(io.StringIO(line)))
        except StopIteration:
            return []

    @staticmethod
    def _column_index(header: list[str], name: str) -> int:
        """Return the index of `name` in the header, or -1 when absent."""
        for index, column in enumerate(header):
            if column.strip() == name:
                return index
        return -1

    @staticmethod
    def _is_date(value: str) -> bool:
        """True when `value` looks like a YYYY-MM-DD date."""
        return len(value) == 10 and value[4] == "-" and value[7] == "-"

    def download_by_date_range(self, base_url: str, start_date: dt.datetime,
                               end_date: dt.datetime) -> list[dict]:
        """Download IBTrACS tropical cyclone data for the given date range.

        Streams the CSV response line-by-line, skipping the units row (row 2),
        and only keeps records whose ISO_TIME falls within [start_date, end_date].
        The full multi-hundred-MB dataset is never materialized in memory.

        The ISO_TIME column is resolved by name from the header row, because
        its position is not stable across IBTrACS releases.
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
            iso_time_index = -1
            row_count = 0
            kept_count = 0

            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                row_count += 1

                # Row 1: header
                if header is None:
                    header = self._parse_line(line)
                    iso_time_index = self._column_index(header, self.ISO_TIME_COLUMN)
                    if iso_time_index < 0:
                        self.logger.error(
                            f"IBTrACS header has no {self.ISO_TIME_COLUMN} column. "
                            f"First columns: {header[:8]}"
                        )
                        return []
                    continue

                # Row 2: units — skip
                if row_count == 2:
                    continue

                fields = self._parse_line(line)
                if len(fields) <= iso_time_index:
                    continue

                record_date = fields[iso_time_index].strip()[:10]
                if not self._is_date(record_date):
                    continue

                if start_str <= record_date < end_str:
                    # Only now build the full dict
                    row_dict = dict(zip(header, fields, strict=False))
                    filtered.append(row_dict)
                    kept_count += 1

            self.logger.info(f"Scanned {row_count} rows, kept {kept_count} records for the date range")
            return filtered
        finally:
            response.close()
