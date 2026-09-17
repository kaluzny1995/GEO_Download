from __future__ import annotations
import abc
import csv
import io
import datetime as dt
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from util import setup_logger


class BaseDownloader(abc.ABC):
    """Abstract base class for all data source downloaders."""

    __slots__ = ("session", "timeout", "logger")

    def __init__(self, timeout: int = 30, logger=None, log_folder: str | None = None):
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

    def _extract_features(self, data: dict, source_name: str = "") -> list[dict]:
        """Extract features array from a dict response. Returns empty list if not found."""
        return data.get("features", [])

    def _get_json(self, url: str) -> list | dict | None:
        """Fetch JSON from URL, return None on error."""
        self.logger.info(f"Fetching: {url}")
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _download_csv(self, url: str) -> list[dict]:
        """Download CSV from URL and return list of dicts."""
        self.logger.info(f"Downloading CSV from: {url}")
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
        records = list(reader)
        self.logger.info(f"Downloaded {len(records)} records")
        return records

    def _download_csv_with_filter(self, url: str, filter_func=None) -> list[dict]:
        """Download CSV from URL with optional custom filter/parser.

        Args:
            url: URL to download from
            filter_func: Optional callable that takes (text: str) -> list[dict]
                         If provided, uses this instead of default DictReader parsing.
        """
        self.logger.info(f"Downloading CSV from: {url}")
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

        if filter_func:
            records = filter_func(response.text)
        else:
            reader = csv.DictReader(io.StringIO(response.text))
            records = list(reader)

        self.logger.info(f"Downloaded {len(records)} records")
        return records
