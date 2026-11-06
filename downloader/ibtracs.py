from __future__ import annotations

import atexit
import csv
import datetime as dt
import logging
import os
import shutil
import signal
import tempfile
import threading
import time

import requests

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode


class IBTrACSDownloader(BaseDownloader):
    """Downloads global tropical cyclone best-track data from NOAA IBTrACS.

    IBTrACS provides the most complete global tropical cyclone
    data, merging best-track data from WMO Regional Specialized Meteorological
    Centres worldwide. Data includes storm position, wind speed, pressure,
    and landfall information.

    Memory-optimised: the upstream CSV is streamed once to a temporary file per
    run (never held in memory), and every requested day is filtered from that
    file with ``csv.reader``. The full multi-hundred-MB dataset is never
    materialized in memory; a multi-day run also downloads it only once.

    The transfer is bounded: each attempt has a wall-clock deadline and a
    stalled stream is retried from scratch, so a slow NCEI response fails
    cleanly instead of hanging until Airflow's execution timeout.

    Every row's point is stamped with ``geocode_country``/``geocode_state``
    (shared lookup ``data/reverse_geocode.csv``): only rows within
    ``geocode_distance_km`` of land may query the API — an open-ocean
    coordinate always answers with no country anyway — but cached answers of
    far rows are stamped too, which is exactly what the ETL used to embed.
    """

    ISO_TIME_COLUMN = "ISO_TIME"

    __slots__ = (
        "_cache_path",
        "_cache_url",
        "_dataset",
        "_download_attempts",
        "_download_chunk_size",
        "_download_timeout",
        "_geocode_distance_km",
        "_progress_log_bytes",
        "_retry_backoff_seconds",
        "_temp_dir",
    )

    def __init__(
        self,
        timeout: int = 60,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        dataset: str = "last3years",
        reverse_geocode_file: str | None = None,
        geocode_distance_km: int = 100,
        download_timeout: int = 300,
        download_chunk_size: int = 1024 * 1024,
        download_attempts: int = 3,
        download_retry_backoff_seconds: float = 5.0,
        progress_log_bytes: int = 2 * 1024 * 1024,
    ):
        super().__init__(
            timeout=timeout, logger=logger, log_folder=log_folder, reverse_geocode_file=reverse_geocode_file
        )
        settings = {
            "geocode_distance_km": geocode_distance_km,
            "download_timeout": download_timeout,
            "download_chunk_size": download_chunk_size,
            "download_attempts": download_attempts,
            "download_retry_backoff_seconds": download_retry_backoff_seconds,
            "progress_log_bytes": progress_log_bytes,
        }
        for name, value in settings.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")

        self._dataset = dataset
        self._geocode_distance_km = geocode_distance_km
        self._download_timeout = download_timeout
        self._download_chunk_size = download_chunk_size
        self._download_attempts = download_attempts
        self._retry_backoff_seconds = download_retry_backoff_seconds
        self._progress_log_bytes = progress_log_bytes
        self._cache_path: str | None = None
        self._cache_url: str | None = None
        self._temp_dir: str | None = None

    def _build_url(self, base_url: str) -> str:
        """Build the download URL for the IBTrACS dataset."""
        return f"{base_url}/ibtracs.{self._dataset}.list.v04r01.csv"

    def _near_land(self, record: dict) -> bool:
        """Whether the row sits within ``geocode_distance_km`` of land.

        Mirrors the ETL's comparison, which reads ``dist2land`` after the
        plain-table integer cast — ``"100.9"`` counts as near-land there, so the
        truncation happens here too. Blank or unusable distances never match.
        """
        value = str(record.get("DIST2LAND") or "").strip()
        if not value:
            return False
        try:
            return int(float(value)) <= self._geocode_distance_km
        except ValueError:
            return False

    def _ensure_temp_dir(self) -> str:
        """Create (once) the temporary directory that holds this run's dataset file."""
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="geo_ibtracs_")
            atexit.register(shutil.rmtree, self._temp_dir, ignore_errors=True)
        return self._temp_dir

    def _download_to(self, url: str, path: str) -> None:
        """Stream *url* to *path* within its configured download budget.

        Raises:
            requests.exceptions.RequestException: On an HTTP/network error, an
                empty/truncated body, or when the attempt exceeds its wall-clock
                deadline.
        """
        started = time.monotonic()
        downloaded = 0
        last_logged = 0
        response = None
        try:
            response = self.session.get(url, timeout=(self.timeout, self.timeout), stream=True)
            response.raise_for_status()
            with open(path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=self._download_chunk_size):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.monotonic() - started

                    if downloaded - last_logged >= self._progress_log_bytes:
                        last_logged = downloaded
                        self.logger.info(f"IBTrACS download progress: {downloaded / 1024**2:.0f} MiB in {elapsed:.0f}s")

                    if elapsed > self._download_timeout:
                        raise requests.exceptions.Timeout(
                            f"exceeded the {self._download_timeout}s download budget "
                            f"after {downloaded / 1024**2:.1f} MiB"
                        )

            if downloaded == 0:
                raise requests.exceptions.ConnectionError("IBTrACS returned an empty response body")
            self.logger.info(
                f"Downloaded IBTrACS CSV: {downloaded / 1024**2:.1f} MiB in {time.monotonic() - started:.1f}s"
            )
        finally:
            if response is not None:
                response.close()

    def _download_attempt(self, url: str, path: str) -> None:
        """Run one transfer attempt under a wall-clock deadline.

        The per-chunk check in :meth:`_download_to` covers a stream that trickles
        in; ``SIGALRM`` also covers the *blocking* part before the first chunk
        (DNS/connect/TLS, including urllib3's own connect retries), which no
        per-read socket timeout can bound as a whole.
        """
        if not hasattr(signal, "SIGALRM") or threading.current_thread() is not threading.main_thread():
            self._download_to(url, path)
            return

        def _expired(_signum: int, _frame: object) -> None:
            raise requests.exceptions.Timeout(f"exceeded the {self._download_timeout}s download budget")

        previous_handler = signal.signal(signal.SIGALRM, _expired)
        signal.setitimer(signal.ITIMER_REAL, self._download_timeout)
        try:
            self._download_to(url, path)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _download_dataset(self, url: str) -> str | None:
        """Return a local copy of the dataset CSV, downloading it at most once per run.

        The file is reused by every day of a multi-day range. A failed or
        over-budget transfer is retried ``download_attempts`` times from
        scratch; after the last failure ``None`` is returned and the caller
        treats it like any other fetch error (no records for that day).
        """
        if self._cache_url == url and self._cache_path is not None and os.path.exists(self._cache_path):
            self.logger.info(f"Using the IBTrACS CSV already downloaded in this run: {self._cache_path}")
            return self._cache_path

        for attempt in range(1, self._download_attempts + 1):
            path = os.path.join(self._ensure_temp_dir(), "ibtracs.csv")
            try:
                self.logger.info(f"Downloading IBTrACS data from: {url}")
                self._download_attempt(url, path)
            except requests.exceptions.RequestException as error:
                if os.path.exists(path):
                    os.remove(path)
                if attempt >= self._download_attempts:
                    self.logger.error(f"Failed to fetch IBTrACS after {self._download_attempts} attempts: {error}")
                    return None
                delay = self._retry_backoff_seconds * 2 ** (attempt - 1)
                self.logger.warning(
                    f"IBTrACS download attempt {attempt}/{self._download_attempts} failed ({error}) — "
                    f"retrying in {delay:.0f}s"
                )
                time.sleep(delay)
            else:
                self._cache_url = url
                self._cache_path = path
                return path

        return None

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

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download IBTrACS tropical cyclone data for the given date range.

        Downloads the CSV once per run to a temporary file, then parses it with
        ``csv.reader``, skipping the units row (row 2) and keeping only records
        whose ISO_TIME falls within [start_date, end_date). The full dataset is
        never held in memory, and later days of the same run reuse the file.

        The ISO_TIME column is resolved by name from the header row, because
        its position is not stable across IBTrACS releases.
        """
        url = self._build_url(base_url)
        start_str = self._format_date(start_date)
        end_str = self._format_date(end_date)

        self.logger.info(f"Filtering for period: {start_str} to {end_str}")

        path = self._download_dataset(url)
        if path is None:
            return []

        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                if not header:
                    self.logger.error("IBTrACS CSV is empty")
                    return []
                iso_time_index = self._column_index(header, self.ISO_TIME_COLUMN)
                if iso_time_index < 0:
                    self.logger.error(
                        f"IBTrACS header has no {self.ISO_TIME_COLUMN} column. First columns: {header[:8]}"
                    )
                    return []

                # Row 2: units — skip
                next(reader, None)

                filtered: list[dict] = []
                row_count = 0
                kept_count = 0
                for fields in reader:
                    row_count += 1
                    if len(fields) <= iso_time_index:
                        continue

                    record_date = fields[iso_time_index].strip()[:10]
                    if not self._is_date(record_date):
                        continue

                    if start_str <= record_date < end_str:
                        # Only now build the full dict
                        filtered.append(dict(zip(header, fields, strict=False)))
                        kept_count += 1
        except OSError as error:
            self.logger.error(f"Could not read the downloaded IBTrACS CSV: {error}")
            return []

        self.logger.info(f"Scanned {row_count} rows, kept {kept_count} records for the date range")
        stamp_geocode(
            filtered,
            output=self.reverse_geocode_file,
            latitude_key="LAT",
            longitude_key="LON",
            fetch_filter=self._near_land,
            embed_all=True,
            logger=self.logger,
        )
        return filtered
