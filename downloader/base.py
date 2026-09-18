from __future__ import annotations
import abc
import csv
import io
import logging
import datetime as dt
from collections.abc import Callable

import requests
from requests.exceptions import RequestException
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from util import setup_logger


class BaseDownloader(abc.ABC):
    """Abstract base class for all data source downloaders."""

    session: requests.Session
    timeout: int
    logger: logging.Logger

    def __init__(self, timeout: int = 30, logger: logging.Logger | None = None,
                 log_folder: str | None = None) -> None:
        self.timeout = timeout
        if logger:
            self.logger = logger
        elif log_folder:
            self.logger = setup_logger(
                name=log_folder,
                log_file=f"logs/{log_folder}/{log_folder}_{dt.datetime.now().isoformat()}.log",
            )
        else:
            self.logger = setup_logger(name="downloader",
                                       log_file=f"logs/downloader_{dt.datetime.now().isoformat()}.log")
        self.session = self._create_session()

    @staticmethod
    def _create_session() -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
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

    @staticmethod
    def _format_date(date: dt.datetime) -> str:
        """Format datetime as YYYY-MM-DD string."""
        return date.strftime("%Y-%m-%d")

    @staticmethod
    def _format_datetime(date: dt.datetime) -> str:
        """Format datetime as YYYY-MM-DD HH:MM:SS string."""
        return date.strftime("%Y-%m-%d %H:%M:%S")

    def _validate_dict_response(self, data: dict | None, source_name: str) -> dict | None:
        """Validate API response is a non-empty dict. Returns None if invalid."""
        if not data or not isinstance(data, dict):
            self.logger.warning(f"No data received from {source_name} API")
            return None
        return data

    def _validate_list_response(self, data: list | None, source_name: str) -> list | None:
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
        response = None
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

    def _download_csv_with_filter(self, url: str, filter_func: Callable[[str], list[dict]] | None = None) -> list[dict]:
        """Download CSV from URL with optional custom filter/parser.

        Args:
            url: URL to download from
            filter_func: Optional callable that takes (text: str) -> list[dict]
                         If provided, uses this instead of default DictReader parsing.
        """
        self.logger.info(f"Downloading CSV from: {url}")
        response = self._fetch_response(url)
        if response is None:
            return []

        try:
            text = response.text
        finally:
            response.close()

        if filter_func:
            records = filter_func(text)
        else:
            reader = csv.DictReader(io.StringIO(text))
            records = list(reader)

        self.logger.info(f"Downloaded {len(records)} records")
        return records

    def _fetch_response(self, url: str) -> requests.Response | None:
        """Fetch a response from URL, return None on error."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            self.logger.info("Download successful")
            return response
        except RequestException as e:
            self.logger.error(f"Download failed: {e}")
            return None
