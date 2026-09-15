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
