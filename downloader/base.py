from __future__ import annotations

import abc
import csv
import datetime as dt
import logging

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from reverse_geocode import DEFAULT_REVERSE_GEOCODE_FILE
from util import setup_logger

# Identify the client explicitly instead of the default `python-requests/x.y` agent:
# some upstreams (NOAA/NCEI included) throttle or stall unattributed scripted clients.
USER_AGENT = "GEO_Download/1.0"


class BaseDownloader(abc.ABC):
    """Abstract base class for all data source downloaders."""

    session: requests.Session
    timeout: int
    logger: logging.Logger
    reverse_geocode_file: str

    def __init__(
        self,
        timeout: int = 30,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        reverse_geocode_file: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.reverse_geocode_file = reverse_geocode_file or DEFAULT_REVERSE_GEOCODE_FILE
        if logger:
            self.logger = logger
        elif log_folder:
            self.logger = setup_logger(
                name=log_folder,
                log_file=f"logs/{log_folder}/{log_folder}_{dt.datetime.now().isoformat()}.log",
            )
        else:
            self.logger = setup_logger(
                name="downloader", log_file=f"logs/downloader_{dt.datetime.now().isoformat()}.log"
            )
        self.session = self._create_session()

    @staticmethod
    def _create_session() -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        retries = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        return session

    @abc.abstractmethod
    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download data for a specific date range. Returns list of record dicts."""

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Create the reference files this source needs beside its day CSVs.

        Called by ``run_download`` once the CSVs of the range are written —
        for sources whose ETL joins extra data this is where that reference
        is built when it is missing. The default does nothing: most sources
        only produce CSVs.

        Args:
            api_url: The endpoint configured for this source.
        """
        return None

    def close(self) -> None:
        """Release the HTTP connection pool held by this downloader.

        Each run downloads one source in a short-lived process, so the OS
        would close the sockets at exit anyway. Closing explicitly keeps the
        downloader safe to reuse from a long-lived process (tests, scripts,
        future multi-source runs) and makes the resource lifetime visible at
        the call site.
        """
        self.session.close()

    def __enter__(self) -> BaseDownloader:
        """Return this downloader for ``with`` blocks."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close the HTTP session when the ``with`` block ends."""
        self.close()

    @staticmethod
    def _format_date(date: dt.datetime) -> str:
        """Format datetime as YYYY-MM-DD string."""
        return date.strftime("%Y-%m-%d")

    @staticmethod
    def _format_datetime(date: dt.datetime) -> str:
        """Format datetime as YYYY-MM-DD HH:MM:SS string."""
        return date.strftime("%Y-%m-%d %H:%M:%S")

    def _validate_dict_response(self, data: list | dict | None, source_name: str) -> dict | None:
        """Validate API response is a non-empty dict. Returns None if invalid."""
        if not data or not isinstance(data, dict):
            self.logger.warning(f"No data received from {source_name} API")
            return None
        return data

    def _validate_list_response(self, data: list | dict | None, source_name: str) -> list | None:
        """Validate API response is a non-empty list. Returns None if invalid."""
        if not data or not isinstance(data, list):
            self.logger.warning(f"No data received from {source_name} API")
            return None
        return data

    @staticmethod
    def _extract_features(data: dict) -> list[dict]:
        """Extract features array from a dict response. Returns empty list if not found."""
        return data.get("features", [])

    def _get_json(self, url: str) -> list | dict | None:
        """Fetch JSON from URL, return None on error."""
        self.logger.info(f"Fetching: {url}")
        response = None
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data
        except RequestException as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None
        finally:
            if response is not None:
                response.close()

    def _download_csv(self, url: str) -> list[dict]:
        """Download CSV from URL and return list of dicts.

        Streams the response line-by-line to avoid loading the entire body
        into memory at once.
        """
        self.logger.info(f"Downloading CSV from: {url}")
        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            self.logger.info("Download successful")
        except RequestException as e:
            self.logger.error(f"Download failed: {e}")
            return []

        try:
            lines = (line.decode("utf-8", errors="replace") for line in response.iter_lines())
            reader = csv.DictReader(lines)
            records = list(reader)
            self.logger.info(f"Downloaded {len(records)} records")
            return records
        finally:
            response.close()
