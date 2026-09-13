from __future__ import annotations
import csv
import io
import datetime as dt
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from util import setup_logger


class USGSDownloader:
    __slots__ = ("session", "timeout", "logger")

    def __init__(self, timeout=30, logger=None):
        self.session = requests.Session()
        self.timeout = timeout

        self.logger = logger or setup_logger(name="usgs",
                                             log_file=f"logs/usgs/USGS_{dt.datetime.now().isoformat()}.log")

        retries = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))

    def download_csv(self, url: str) -> list[dict]:
        """ Downloads CSV from USGS feed URL and returns list of dicts """
        self.logger.info(f"Downloading earthquake data from: {url}")

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

        reader = csv.DictReader(io.StringIO(response.text))
        earthquakes = list(reader)

        self.logger.info(f"Downloaded {len(earthquakes)} earthquake records")
        return earthquakes

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """ Downloads earthquake data for a specific date range """
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        url = f"{base_url}?format=csv&starttime={start_str}&endtime={end_str}"
        self.logger.info(f"Downloading earthquake data for period: {start_str} to {end_str}")

        return self.download_csv(url)
