from __future__ import annotations

import csv
import datetime as dt
import logging
import os
from pathlib import Path
from typing import Any

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode

FLOOD_LEVELS: tuple[str, ...] = ("major", "moderate", "minor", "action")
"""NWS flood categories from the most to the least severe, spelled the way NWPS spells them."""

NO_FLOODING = "no_flooding"
"""NWS category of a stage below every flood threshold the gauge defines."""

FLOOD_CATEGORY_COLUMNS: tuple[str, ...] = (
    "site_id",
    "identifier",
    "site_name",
    "state",
    "latitude",
    "longitude",
    *(f"{level}_stage_ft" for level in reversed(FLOOD_LEVELS)),
)
"""Columns of the flood-category reference, in the order they are written."""


class USGSNWISDownloader(BaseDownloader):
    """Downloads daily streamflow and gauge height from the USGS NWIS WaterServices API.

    Queries the instantaneous-value service (``iv``) for the discharge parameter
    (``00060``) *and* the gauge-height parameter (``00065``) in one request and
    aggregates the 5-minute readings per gauge and day in code: the discharge becomes
    the day's mean (the statistic the daily-value service publishes, only computed by
    us here) and the gauge height the day's peak — the daily-value service publishes no
    daily ``00065`` values at all, so the stage can only come from instantaneous data.
    Readings that are not numbers (``Ice`` and friends) are skipped.

    Every gauge point is reverse-geocoded into ``geocode_state`` (shared lookup
    ``data/reverse_geocode.csv``), the subdivision the ETL used to resolve itself.
    Beside the day files the download keeps GEO_ETL's flood-category reference
    (``flood_categories_file``) present and labels every record's peak stage with the
    NWS category it reached — see :meth:`ensure_auxiliary_files`.
    """

    DEFAULT_NWPS_API_URL = "https://api.water.noaa.gov/nwps/v1/gauges"
    """NWS National Water Prediction Service gauge endpoint, one request per gauge."""

    DEFAULT_FLOOD_CATEGORIES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "usgs_flood_categories.csv")
    """The reference GEO_ETL joins on every day (``params.flood_categories_file`` in ``config.json``)."""

    def __init__(
        self,
        timeout: int = 60,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        sites: str = "01646500",
        parameter_code: str = "00060",
        stage_parameter_code: str = "00065",
        nwps_api_url: str | None = None,
        flood_categories_file: str | None = None,
        reverse_geocode_file: str | None = None,
    ):
        """Configure the gauges, the parameters and the NWS reference to maintain.

        Args:
            timeout: Per-request timeout in seconds.
            logger: Logger to report to instead of the default one.
            log_folder: Log folder naming the default logger when no logger is given.
            sites: Comma-separated USGS site numbers to query.
            parameter_code: Comma-separated discharge parameters, one row per gauge and day.
            stage_parameter_code: Gauge-height parameter aggregated into ``gauge_height``.
            nwps_api_url: NWS gauge endpoint the flood categories are read from.
            flood_categories_file: Reference GEO_ETL joins next to the day CSVs.
            reverse_geocode_file: Shared geocode lookup to stamp ``geocode_state``.
        """
        super().__init__(
            timeout=timeout, logger=logger, log_folder=log_folder, reverse_geocode_file=reverse_geocode_file
        )
        self._sites = sites
        self._metric_parameters = tuple(code.strip() for code in parameter_code.split(",") if code.strip())
        self._stage_parameter = stage_parameter_code.strip()
        self.nwps_api_url = (nwps_api_url or self.DEFAULT_NWPS_API_URL).rstrip("/")
        self.flood_categories_file = flood_categories_file or self.DEFAULT_FLOOD_CATEGORIES_FILE
        self._flood_categories: dict[str, dict[str, str]] | None = None

    def _build_url(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> str:
        """Build the API query URL for the discharge and the gauge-height parameter."""
        codes = dict.fromkeys(code for code in (*self._metric_parameters, self._stage_parameter) if code)
        params = [
            "format=json",
            f"sites={self._sites}",
            f"parameterCd={','.join(codes)}",
            f"startDT={self._format_date(start_date)}",
            f"endDT={self._format_date(end_date)}",
        ]
        return f"{base_url}?{'&'.join(params)}"

    @staticmethod
    def _numbers(readings: list[dict]) -> list[float]:
        """The readings that are actual numbers — ``Ice`` and friends are dropped."""
        numbers = []
        for reading in readings:
            value = reading.get("value")
            if value is None:
                continue
            try:
                numbers.append(float(value))
            except (TypeError, ValueError):
                continue
        return numbers

    @classmethod
    def _mean(cls, readings: list[dict]) -> float | None:
        """Mean of the day's readings, ``None`` when none of them is a number."""
        numbers = cls._numbers(readings)
        return sum(numbers) / len(numbers) if numbers else None

    @classmethod
    def _peak(cls, readings: list[dict]) -> float | None:
        """Highest of the day's readings, ``None`` when none of them is a number."""
        numbers = cls._numbers(readings)
        return max(numbers) if numbers else None

    @staticmethod
    def _qualifiers(readings: list[dict]) -> str:
        """Distinct qualifier flags of the day's readings, in first-seen order."""
        return ",".join(dict.fromkeys(flag for reading in readings for flag in reading.get("qualifiers") or []))

    @staticmethod
    def _format_number(value: float) -> str:
        """The value rounded to two decimals without the trailing zeros (``2320``, ``2.85``)."""
        text = f"{value:.2f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _build_records(self, data: dict) -> list[dict]:
        """Aggregate the instantaneous readings of a response into one record per gauge and day.

        Args:
            data: Parsed NWIS response (``value.timeSeries``).

        Returns:
            One record per (gauge, day, discharge parameter), sorted by gauge and day,
            every record carrying the same keys in the same order — ``save_csv`` takes
            its columns from the first record. ``value`` is the day's mean discharge,
            ``gauge_height`` the day's peak stage (empty when the day has none) and
            ``flood_category`` is filled in by :meth:`download_by_date_range` from the
            NWS reference.
        """
        days: dict[tuple[str, str], dict[str, Any]] = {}
        for time_series in data.get("value", {}).get("timeSeries", []):
            site_info = time_series.get("sourceInfo", {})
            site_code = (site_info.get("siteCode") or [{}])[0].get("value", "")
            if not site_code:
                continue
            variable = time_series.get("variable", {})
            parameter = (variable.get("variableCode") or [{}])[0].get("value", "")
            unit = variable.get("unit", {}).get("unitCode", "") if isinstance(variable.get("unit"), dict) else ""
            geo = site_info.get("geoLocation", {}).get("geogLocation", {})
            for values_obj in time_series.get("values") or [{}]:
                for reading in values_obj.get("value") or []:
                    date = reading.get("dateTime", "")[:10]
                    if not date:
                        continue
                    day = days.setdefault(
                        (site_code, date),
                        {
                            "site_name": site_info.get("siteName", ""),
                            "latitude": geo.get("latitude", ""),
                            "longitude": geo.get("longitude", ""),
                            "units": {},
                            "readings": {},
                        },
                    )
                    day["units"].setdefault(parameter, unit)
                    day["readings"].setdefault(parameter, []).append(reading)

        records = []
        for (site_code, date), day in sorted(days.items()):
            gauge_height = self._peak(day["readings"].get(self._stage_parameter, []))
            for parameter in self._metric_parameters:
                readings = day["readings"].get(parameter)
                if not readings:
                    continue
                mean = self._mean(readings)
                if mean is None:
                    continue
                records.append(
                    {
                        "site_id": f"USGS-{site_code}",
                        "site_name": day["site_name"],
                        "parameter_code": parameter,
                        "date": date,
                        "value": self._format_number(mean),
                        "unit": day["units"].get(parameter, ""),
                        "qualifiers": self._qualifiers(readings),
                        "gauge_height": self._format_number(gauge_height) if gauge_height is not None else "",
                        "flood_category": "",
                        "latitude": day["latitude"],
                        "longitude": day["longitude"],
                    }
                )
        return records

    def _load_flood_categories(self) -> dict[str, dict[str, str]]:
        """The flood-category reference keyed by site id, read from disk on first use."""
        if self._flood_categories is None:
            rows: dict[str, dict[str, str]] = {}
            if os.path.exists(self.flood_categories_file) and os.path.getsize(self.flood_categories_file) > 0:
                with open(self.flood_categories_file, newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        site_id = (row.get("site_id") or "").strip()
                        if site_id:
                            rows[site_id] = {
                                column: (row.get(column) or "").strip() for column in FLOOD_CATEGORY_COLUMNS
                            }
            self._flood_categories = rows
        return self._flood_categories

    def _write_flood_categories(self, rows: dict[str, dict[str, str]]) -> None:
        """Write the flood-category reference, one row per gauge, sorted by site id."""
        folder = os.path.dirname(self.flood_categories_file)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(self.flood_categories_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FLOOD_CATEGORY_COLUMNS))
            writer.writeheader()
            for site_id in sorted(rows):
                writer.writerow({column: rows[site_id].get(column, "") for column in FLOOD_CATEGORY_COLUMNS})

    @staticmethod
    def _stage_text(stage: Any) -> str:
        """A stage from the NWS reference as written to the CSV (``""`` when undefined)."""
        try:
            number = float(stage)
        except (TypeError, ValueError):
            return ""
        if number <= -9999:
            return ""
        return USGSNWISDownloader._format_number(number)

    def _fetch_flood_category(self, site_code: str) -> dict[str, str] | None:
        """Read one gauge's NWS flood thresholds, ``None`` when the gauge is unknown to NWPS.

        Args:
            site_code: Bare USGS site number (``01646500``).

        Returns:
            The reference row of the gauge in :data:`FLOOD_CATEGORY_COLUMNS` order, or
            ``None`` when NWPS has no gauge for the site — the day files are written
            either way and the site simply carries no flood category.
        """
        data = self._get_json(f"{self.nwps_api_url}/{site_code}")
        data = self._validate_dict_response(data, "NWS NWPS")
        if not data:
            return None
        payload = data.get("gaugeGauge")
        gauge = payload if isinstance(payload, dict) else data
        state = gauge.get("state")
        flood = gauge.get("flood") or {}
        categories = flood.get("categories") or {}
        row = {
            "site_id": f"USGS-{site_code}",
            "identifier": gauge.get("lid", ""),
            "site_name": gauge.get("name", ""),
            "state": state.get("abbreviation", "") if isinstance(state, dict) else (state or ""),
            "latitude": gauge.get("latitude", ""),
            "longitude": gauge.get("longitude", ""),
        }
        for level in FLOOD_LEVELS:
            row[f"{level}_stage_ft"] = self._stage_text((categories.get(level) or {}).get("stage"))
        return row

    def _ensure_flood_categories(self, site_codes: list[str]) -> None:
        """Add the gauges the flood-category reference is missing and persist it.

        Args:
            site_codes: Bare USGS site numbers that have to be covered. Gauges NWPS
                does not know are left out; the next run tries them again.
        """
        rows = self._load_flood_categories()
        added = 0
        for site_code in site_codes:
            site_id = f"USGS-{site_code}"
            if site_id in rows:
                continue
            row = self._fetch_flood_category(site_code)
            if row:
                rows[site_id] = row
                added += 1
        if added:
            self._write_flood_categories(rows)
            self.logger.info(f"Added {added} gauges to flood-category reference {self.flood_categories_file}")

    def _flood_category(self, site_id: str, gauge_height: str) -> str:
        """The NWS category a day's peak stage reached, ``""`` when it cannot be classified.

        Args:
            site_id: Site id of the gauge (``USGS-01646500``).
            gauge_height: Day's peak stage as written into the record (``""`` without one).

        Returns:
            The highest category whose stage threshold the peak is at or above
            (``major`` … ``action``), ``no_flooding`` when the gauge defines thresholds
            and the peak clears none of them, ``""`` when the gauge is unknown or its
            reference carries no threshold.
        """
        if not gauge_height:
            return ""
        row = self._load_flood_categories().get(site_id)
        if not row:
            return ""
        thresholds = [(level, row[f"{level}_stage_ft"]) for level in FLOOD_LEVELS if row[f"{level}_stage_ft"]]
        if not thresholds:
            return ""
        try:
            peak = float(gauge_height)
        except ValueError:
            return ""
        for level, stage in thresholds:
            if peak >= float(stage):
                return level
        return NO_FLOODING

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download the gauges' daily streamflow and gauge height for the date range.

        The instantaneous readings of the range are aggregated per gauge and day, the
        gauges are looked up in the NWS flood-category reference (built when missing)
        and every record's peak stage is labelled with the category it reached.

        Args:
            base_url: NWIS endpoint configured for this source.
            start_date: First day to query.
            end_date: Last day to query, inclusive of the range ``run_download`` builds.

        Returns:
            The records to write to the day's CSV, an empty list without a usable
            response.
        """
        self.logger.info(f"Downloading USGS NWIS data for {start_date.date()} to {end_date.date()}")
        self.logger.info(f"  sites={self._sites}, parameters={','.join(self._metric_parameters)}")

        url = self._build_url(base_url, start_date, end_date)
        data = self._get_json(url)

        data = self._validate_dict_response(data, "USGS NWIS")
        if not data:
            return []

        time_series_list = data.get("value", {}).get("timeSeries", [])
        self.logger.info(f"Received {len(time_series_list)} time series")

        records = self._build_records(data)
        if records:
            site_codes = sorted({record["site_id"].removeprefix("USGS-") for record in records})
            self._ensure_flood_categories(site_codes)
            for record in records:
                record["flood_category"] = self._flood_category(record["site_id"], record["gauge_height"])

        stamp_geocode(records, output=self.reverse_geocode_file, columns=("geocode_state",), logger=self.logger)
        self.logger.info(f"Downloaded {len(records)} USGS NWIS records total")
        return records

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Build the NWS flood-category reference GEO_ETL joins beside the day CSVs.

        ``data/usgs_flood_categories.csv`` carries one row per gauge with
        its NWS identifier, its location and the ``action``/``minor``/``moderate``/
        ``major`` stage thresholds GEO_ETL reads on every day to spell out how high the
        gauge stood against them. Without it every day keeps those ``NULL``, so a run
        that finds a reference missing gauges builds one from the NWS gauge endpoint —
        one request per configured gauge, also after a range that wrote no records.

        An existing gauge is left alone; ``run_download`` calls this after the day
        CSVs were written, so a gauge NWPS does not know only logs a warning here and
        its days keep an empty ``flood_category`` until NWPS carries it.

        Args:
            api_url: NWIS endpoint configured for this source (the categories come
                from the NWS gauge endpoint, not from it).
        """
        self.logger.info(f"Ensuring flood categories of sites={self._sites} (NWIS endpoint {api_url})")
        self._ensure_flood_categories([code.strip() for code in self._sites.split(",") if code.strip()])
