from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode


class OpenMeteoFloodDownloader(BaseDownloader):
    """Downloads river discharge data from the Open-Meteo Flood API (GloFAS).

    Queries daily river discharge (m3/s) for a list of major world rivers
    defined in data/rivers.json. Every river point is reverse-geocoded into
    ``geocode_country``/``geocode_state`` (shared lookup
    ``data/reverse_geocode.csv``), the pair the ETL used to resolve itself.

    Next to the discharge the query asks for the ensemble statistics of the
    forecast days (``river_discharge_mean``/``_median``/``_p25``/``_p75``).
    They are only meaningful while the day is still a forecast, so a row
    carries them only when it is a forecast row *and* its day is today or
    later — the analysis day of the file (and every row of a backfill, which
    has become consolidated in the meantime) keeps them ``NULL``, instead of
    the degenerate ``p25 == p75 == discharge`` the API returns for
    consolidated data.

    Beside the day files the download keeps GEO_ETL's threshold reference
    (``thresholds_file``) present — see :meth:`ensure_auxiliary_files`.
    """

    DEFAULT_RIVERS_FILE = str(Path(__file__).resolve().parent.parent / "data" / "rivers.json")

    DEFAULT_THRESHOLDS_FILE = str(
        Path(__file__).resolve().parent.parent / "data" / "openmeteo_discharge_thresholds.csv"
    )
    """The reference GEO_ETL joins on every day (``params.thresholds_file`` in ``config.json``)."""

    ENSEMBLE_VARS: tuple[str, ...] = ("mean", "median", "p25", "p75")
    """Ensemble statistics requested next to ``river_discharge``, in column order."""

    ENSEMBLE_COLUMNS: tuple[str, ...] = tuple(f"discharge_{var}_m3s" for var in ENSEMBLE_VARS)
    """CSV columns the ensemble statistics are written to."""

    def __init__(
        self,
        timeout: int = 30,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        rivers_file: str | None = None,
        thresholds_file: str | None = None,
        reverse_geocode_file: str | None = None,
        threshold_baseline_start: str = "2026-09-01",
        threshold_min_days: int = 30,
        threshold_sleep_seconds: float = 1.0,
        threshold_max_hour_waits: int = 1,
        threshold_progress_every_rivers: int = 20,
    ):
        super().__init__(
            timeout=timeout, logger=logger, log_folder=log_folder, reverse_geocode_file=reverse_geocode_file
        )
        if threshold_min_days <= 0:
            raise ValueError("threshold_min_days must be positive")
        if threshold_max_hour_waits < 0:
            raise ValueError("threshold_max_hour_waits must be non-negative")
        if threshold_progress_every_rivers <= 0:
            raise ValueError("threshold_progress_every_rivers must be positive")
        self._rivers_file = rivers_file or self.DEFAULT_RIVERS_FILE
        self.thresholds_file = thresholds_file or self.DEFAULT_THRESHOLDS_FILE
        self.threshold_baseline_start = threshold_baseline_start
        self.threshold_min_days = threshold_min_days
        self.threshold_sleep_seconds = threshold_sleep_seconds
        self.threshold_max_hour_waits = threshold_max_hour_waits
        self._threshold_progress_every_rivers = threshold_progress_every_rivers
        self._rivers = self._load_rivers()

    def _load_rivers(self) -> list[dict]:
        """Load river definitions from JSON file."""
        with open(self._rivers_file) as f:
            return json.load(f)

    def _query_river(self, base_url: str, river: dict, start_date: dt.datetime, end_date: dt.datetime) -> dict | None:
        """Query Open-Meteo Flood API for a single river."""
        daily = ",".join(["river_discharge", *(f"river_discharge_{var}" for var in self.ENSEMBLE_VARS)])
        url = (
            f"{base_url}"
            f"?latitude={river['latitude']}"
            f"&longitude={river['longitude']}"
            f"&daily={daily}"
            f"&start_date={self._format_date(start_date)}"
            f"&end_date={self._format_date(end_date)}"
        )
        result = self._get_json(url)
        return result if isinstance(result, dict) else None

    @classmethod
    def _build_records(
        cls,
        river: dict,
        data: dict,
        analysis_date: dt.date | None = None,
        today: dt.date | None = None,
    ) -> list[dict]:
        """Build flat records from API response for one river.

        Args:
            river: River definition the response was requested for.
            data: Open-Meteo Flood API response.
            analysis_date: The day the file's own analysis row belongs to.
                Days after it are forecast rows of that file.
            today: The day of the download run. Forecast statistics are kept
                only for days ``>= today``; ``None`` keeps them for none.

        Returns:
            One dict per non-null discharge day, all with the same keys —
            the ensemble columns are ``NULL`` where they are not meaningful.
        """
        daily = data.get("daily", {})
        times = daily.get("time", [])
        discharges = daily.get("river_discharge", [])
        ensemble = {var: daily.get(f"river_discharge_{var}", []) for var in cls.ENSEMBLE_VARS}

        records = []
        for index, (date_str, discharge) in enumerate(zip(times, discharges, strict=False)):
            if discharge is None:
                continue
            day = dt.date.fromisoformat(date_str)
            is_forecast = analysis_date is not None and today is not None and day > analysis_date and day >= today
            record = {
                "river_name": river["name"],
                "country": river["country"],
                "latitude": river["latitude"],
                "longitude": river["longitude"],
                "date": date_str,
                "discharge_m3s": discharge,
            }
            for var in cls.ENSEMBLE_VARS:
                values = ensemble[var]
                record[f"discharge_{var}_m3s"] = values[index] if is_forecast and index < len(values) else None
            records.append(record)
        return records

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download river discharge data for all rivers in the date range.

        Queries each river individually and aggregates results. The first day
        of the range is the analysis day of the file, so the ensemble
        statistics of the following days are kept only while those days are
        still forecasts of today's run.
        """
        self.logger.info(f"Downloading Open-Meteo Flood data for {start_date.date()} to {end_date.date()}")
        self.logger.info(f"Monitoring {len(self._rivers)} rivers")

        analysis_date = start_date.date()
        today = dt.date.today()
        all_records: list[dict] = []
        rivers_with_data = 0

        for i, river in enumerate(self._rivers, 1):
            data = self._query_river(base_url, river, start_date, end_date)
            if data and isinstance(data, dict):
                records = self._build_records(river, data, analysis_date=analysis_date, today=today)
                if records:
                    all_records.extend(records)
                    rivers_with_data += 1

            if i % self._threshold_progress_every_rivers == 0:
                self.logger.info(f"  Progress: {i}/{len(self._rivers)} rivers queried")

        stamp_geocode(all_records, output=self.reverse_geocode_file, logger=self.logger)
        self.logger.info(
            f"Downloaded {len(all_records)} discharge records from {rivers_with_data}/{len(self._rivers)} rivers"
        )
        return all_records

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Build the discharge threshold reference when GEO_ETL's copy is missing.

        ``data/openmeteo_discharge_thresholds.csv`` carries one row per river
        with the baseline percentiles GEO_ETL joins on ``river_name`` +
        ``country`` to fill ``danger_rating`` and ``other_metrics``. Without
        it every day keeps those ``NULL``, so a run that finds no file builds
        one with the defaults of ``run_openmeteo_thresholds.py`` (baseline
        from ``2026-09-01`` to today, at least 30 valid days per river).

        An existing file is left alone — refreshing it is what the occasional
        ``python run_openmeteo_thresholds.py`` run (``--restart`` to discard
        it) is for. The build is best effort: when no river could be queried
        the file stays unwritten and the next run tries again, and failures
        are logged by ``run_download`` instead of failing a run whose day
        CSVs were written already. A throttled API is waited out for at most
        one clock hour, so the download does not stall all night.

        Args:
            api_url: Flood API endpoint configured for this source.
        """
        if os.path.exists(self.thresholds_file) and os.path.getsize(self.thresholds_file) > 0:
            self.logger.info(
                f"Threshold reference {self.thresholds_file} already present — "
                "run_openmeteo_thresholds.py rebuilds it when you want fresher percentiles"
            )
            return

        # Local import: run_openmeteo_thresholds imports this module for the downloader.
        from run_openmeteo_thresholds import build_thresholds, make_fetcher, write_thresholds

        baseline_end = dt.date.today().isoformat()
        self.logger.info(
            f"Threshold reference {self.thresholds_file} missing — building it from "
            f"{self.threshold_baseline_start} to {baseline_end}"
        )
        print(
            f"Threshold reference {self.thresholds_file} is missing — building it "
            f"({self.threshold_baseline_start}..{baseline_end})...",
            flush=True,
        )

        start = dt.datetime.strptime(self.threshold_baseline_start, "%Y-%m-%d")
        end = dt.datetime.strptime(baseline_end, "%Y-%m-%d")
        fetch = make_fetcher(
            self,
            api_url,
            start,
            end,
            self.logger,
            sleep=self.threshold_sleep_seconds,
            max_hour_waits=self.threshold_max_hour_waits,
        )
        rows = build_thresholds(
            self,
            api_url,
            self.threshold_baseline_start,
            baseline_end,
            self.threshold_min_days,
            self.logger,
            fetch=fetch,
            progress_every=self._threshold_progress_every_rivers,
        )
        if not rows:
            message = (
                f"No threshold rows could be built from {api_url} — "
                f"{self.thresholds_file} left unwritten, the next run tries again"
            )
            self.logger.error(message)
            print(f"ERROR: {message}", flush=True)
            return

        write_thresholds(rows, self.thresholds_file)
        self.logger.info(f"Built threshold reference {self.thresholds_file} with {len(rows)} rows")
