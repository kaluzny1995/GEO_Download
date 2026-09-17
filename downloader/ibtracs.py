from __future__ import annotations
import csv
import io
import datetime as dt

from downloader.base import BaseDownloader


class IBTrACSDownloader(BaseDownloader):
    """Downloads global tropical cyclone best-track data from NOAA IBTrACS.

    IBTrACS provides the most complete global collection of tropical cyclone
    data, merging best-track data from WMO Regional Specialized Meteorological
    Centres worldwide. Data includes storm position, wind speed, pressure,
    and landfall information.
    """

    __slots__ = ("_dataset",)

    BASE_URL = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"

    def __init__(self, timeout: int = 60, logger=None, log_folder: str | None = None,
                 dataset: str = "last3years"):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._dataset = dataset

    def _build_url(self) -> str:
        """Build the download URL for the IBTrACS dataset."""
        return f"{self.BASE_URL}/ibtracs.{self._dataset}.list.v04r01.csv"

    def _parse_csv(self, text: str) -> list[dict]:
        """Parse IBTrACS CSV text, skipping the units row (row 2)."""
        lines = text.splitlines()
        if len(lines) < 3:
            self.logger.warning("CSV response has fewer than 3 lines, nothing to parse.")
            return []

        filtered_lines = [lines[0]] + lines[2:]
        reader = csv.DictReader(io.StringIO("\n".join(filtered_lines)))
        return list(reader)

    def _filter_by_date(self, records: list[dict], start_date: dt.datetime,
                        end_date: dt.datetime) -> list[dict]:
        """Filter records to only those within the requested date range."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        filtered = []

        for record in records:
            iso_time = record.get("ISO_TIME", "").strip()
            if not iso_time:
                continue
            record_date = iso_time[:10]
            if start_str <= record_date < end_str:
                filtered.append(record)

        return filtered

    def download_by_date_range(self, base_url: str, start_date: dt.datetime,
                               end_date: dt.datetime) -> list[dict]:
        """Download IBTrACS tropical cyclone data for the given date range.

        Downloads the configured IBTrACS dataset (default: last3years) and
        filters records to only those within the requested date range.
        """
        url = self._build_url()
        self.logger.info(f"Downloading IBTrACS data from: {url}")
        self.logger.info(f"Filtering for period: {start_date.date()} to {end_date.date()}")

        response = None
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            self.logger.info("Download successful")
        except Exception as e:
            if response is not None:
                self.logger.error(f"Download failed: {response.status_code} - {e}")
            else:
                self.logger.error(f"Download failed: {e}")
            return []

        all_records = self._parse_csv(response.text)
        self.logger.info(f"Parsed {len(all_records)} total records from IBTrACS")

        filtered = self._filter_by_date(all_records, start_date, end_date)
        self.logger.info(f"Filtered to {len(filtered)} records for the date range")
        return filtered
