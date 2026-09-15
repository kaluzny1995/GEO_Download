from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class USGSEarthquakeDownloader(BaseDownloader):
    """Downloads earthquake data from the USGS FDSN Event Query API."""

    __slots__ = ()

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download earthquake data for a specific date range."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        url = f"{base_url}?format=csv&starttime={start_str}&endtime={end_str}"
        self.logger.info(f"Downloading earthquake data for period: {start_str} to {end_str}")

        return self._download_csv(url)
