from __future__ import annotations

import csv
import datetime as dt
import logging
import os
import urllib.parse
from pathlib import Path
from typing import ClassVar

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode

JURISDICTION_API_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "DMP_JurisdictionalUnits_Public/FeatureServer/0/query"
)
JURISDICTION_WHERE = "JurisdictionalUnitID_sansUS IS NOT NULL AND JurisdictionalUnitID_sansUS <> ''"
JURISDICTION_CODE_FIELD = "JurisdictionalUnitID_sansUS"
JURISDICTION_NAME_FIELD = "JurisdictionalUnitName"


def _state_code(poo_state: str) -> str:
    """Convert an IRWIN point-of-origin state value ('US-CO') to a bare code ('CO')."""
    if poo_state.startswith("US-"):
        return poo_state[3:]
    return poo_state


def _attr(attrs: dict, key: str) -> str | float | int:
    """Read an ArcGIS attribute, mapping null values to an empty string."""
    value = attrs.get(key)
    return "" if value is None else value


def _name_by_code(pairs: set[tuple[str, str]]) -> dict[str, str]:
    """Collapse code/name pairs into a deterministic ``code → name`` map.

    A code carrying several names resolves to the alphabetically first one so
    the written lookup stays stable between refreshes.
    """
    names: dict[str, str] = {}
    for code, name in sorted(pairs):
        names.setdefault(code, name)
    return names


class NIFCDownloader(BaseDownloader):
    """Downloads current wildland fire perimeter data from NIFC ArcGIS REST services.

    Uses the WFIGS (Wildland Fire Interagency Geospatial Services) feature service
    to get current interagency fire perimeters for the United States.

    Field naming on that layer: ``poly_*`` are perimeter-level attributes and
    ``attr_*`` are incident attributes mirrored onto every perimeter. Every name in
    :attr:`_OUT_FIELDS` must exist on the layer — ArcGIS rejects unknown
    ``outFields`` with an HTTP 200 body carrying ``{"error": …}`` rather than a
    non-2xx status, so a stale name fails silently instead of raising.

    The perimeter layer records only the jurisdiction's short code
    (``attr_POOJurisdictionalUnit``, e.g. ``WAOWF``, ``CAYNP``) with no published
    name domain, so the full name is resolved here at download time: every
    record gets ``unit_name`` — the name from the consolidated lookup
    ``data/nifc_unit_names.csv`` (``unit_code, unit_name``), the raw code when
    the lookup does not know it, empty when the code is blank. The lookup is
    built when missing and refreshed from the public
    ``DMP_JurisdictionalUnits_Public`` layer when the data carries an unknown
    code, so the ETL reads ``unit_name`` straight from the source row. Every
    record also carries ``geocode_state`` — the reverse-geocoded subdivision
    of the perimeter point — but only blank-``state`` records ever reach the
    API (the same subset the ETL used to look up), so the ETL reads the
    fallback straight from the source row too.
    """

    _OUT_FIELDS: ClassVar[list[str]] = [
        "poly_IncidentName",
        "poly_IRWINID",
        "poly_FeatureCategory",
        "poly_GISAcres",
        "poly_DateCurrent",
        "attr_IncidentTypeCategory",
        "attr_FireDiscoveryDateTime",
        "attr_PercentContained",
        "attr_POOJurisdictionalAgency",
        "attr_POOJurisdictionalUnit",
        "attr_POOState",
        "attr_InitialLatitude",
        "attr_InitialLongitude",
        "attr_CreatedOnDateTime_dt",
        "attr_ModifiedOnDateTime_dt",
    ]

    DEFAULT_UNIT_NAMES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "nifc_unit_names.csv")
    UNIT_NAMES_FIELDS: ClassVar[list[str]] = ["unit_code", "unit_name"]
    unit_names_file: str | None = None

    def __init__(
        self,
        timeout: int = 30,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        unit_names_file: str | None = None,
        reverse_geocode_file: str | None = None,
    ):
        super().__init__(
            timeout=timeout, logger=logger, log_folder=log_folder, reverse_geocode_file=reverse_geocode_file
        )
        self.unit_names_file = unit_names_file or self.DEFAULT_UNIT_NAMES_FILE

    @staticmethod
    def _build_record(feature: dict) -> dict:
        """Extract a flat record dict from an ArcGIS feature.

        Coordinates come from the feature centroid (requested via
        ``returnCentroid=true``), falling back to the incident's point of origin
        when the service omits it. ``unit_name`` is an empty placeholder here —
        :meth:`_resolve_unit_names` fills it from the lookup once the whole day
        is downloaded (the key must already exist to keep the CSV column order).
        """
        attrs = feature.get("attributes", {})
        centroid = feature.get("centroid") or {}

        latitude = centroid.get("y") or _attr(attrs, "attr_InitialLatitude") or ""
        longitude = centroid.get("x") or _attr(attrs, "attr_InitialLongitude") or ""
        poo_state = _attr(attrs, "attr_POOState")

        return {
            "incident_name": _attr(attrs, "poly_IncidentName"),
            "irwin_id": _attr(attrs, "poly_IRWINID"),
            "fire_number": _attr(attrs, "attr_FireDiscoveryDateTime"),
            "acres": _attr(attrs, "poly_GISAcres"),
            "percent_contained": _attr(attrs, "attr_PercentContained"),
            "fire_type": _attr(attrs, "attr_IncidentTypeCategory"),
            "fire_type_label": _attr(attrs, "poly_FeatureCategory"),
            "jurisdiction": _attr(attrs, "attr_POOJurisdictionalAgency"),
            "jurisdiction_label": _attr(attrs, "attr_POOJurisdictionalUnit"),
            "unit_name": "",
            "state": _state_code(str(poo_state)) if poo_state else "",
            "po_method": poo_state,
            "latitude": latitude,
            "longitude": longitude,
            "poly_date": _attr(attrs, "poly_DateCurrent"),
            "created_on": _attr(attrs, "attr_CreatedOnDateTime_dt"),
            "modified_on": _attr(attrs, "attr_ModifiedOnDateTime_dt"),
        }

    @staticmethod
    def _api_error_message(data: dict) -> str:
        """Render an ArcGIS error payload as a single log line."""
        error = data.get("error", {})
        if not isinstance(error, dict):
            return str(error)
        details = "; ".join(str(item) for item in error.get("details") or [])
        message = error.get("message") or "unknown error"
        return f"{message} ({details})" if details else str(message)

    def _load_unit_names(self) -> dict[str, str]:
        """Read the unit-name lookup CSV into a ``code → name`` map.

        Returns an empty map when no lookup file is configured or the file does
        not exist yet; blank codes and blank names are skipped.
        """
        if not self.unit_names_file or not os.path.exists(self.unit_names_file):
            return {}
        with open(self.unit_names_file, newline="", encoding="utf-8") as handle:
            return {
                code: name
                for row in csv.DictReader(handle)
                if (code := (row.get("unit_code") or "").strip()) and (name := (row.get("unit_name") or "").strip())
            }

    def _write_unit_names(self, names: dict[str, str]) -> None:
        """Write ``names`` to the lookup CSV, creating the directory when needed.

        Args:
            names: ``code → name`` map to persist, sorted by unit code.
        """
        if not self.unit_names_file:
            return
        os.makedirs(os.path.dirname(self.unit_names_file) or ".", exist_ok=True)
        with open(self.unit_names_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.UNIT_NAMES_FIELDS)
            writer.writeheader()
            writer.writerows({"unit_code": code, "unit_name": names[code]} for code in sorted(names))
        self.logger.info(f"  unit-name lookup: {len(names)} codes -> {self.unit_names_file}")

    def _fetch_pairs(self, api_url: str = JURISDICTION_API_URL) -> set[tuple[str, str]]:
        """Download every distinct ``(code, name)`` pair of the jurisdiction layer.

        Args:
            api_url: ArcGIS ``FeatureServer/0/query`` endpoint.

        Returns:
            The distinct non-empty code/name pairs.

        Raises:
            RuntimeError: When the endpoint errors out or returns no usable rows.
        """
        params = {
            "where": JURISDICTION_WHERE,
            "outFields": f"{JURISDICTION_CODE_FIELD},{JURISDICTION_NAME_FIELD}",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
            "f": "json",
        }
        data = self._get_json(f"{api_url}?{urllib.parse.urlencode(params)}")

        if not isinstance(data, dict):
            raise RuntimeError("NIFC jurisdiction layer returned no response — nothing written")

        if "error" in data:
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"NIFC jurisdiction layer rejected the query: {message}")

        features = data.get("features")
        pairs = {
            (str(attrs[JURISDICTION_CODE_FIELD]).strip(), str(attrs[JURISDICTION_NAME_FIELD]).strip())
            for attrs in (feature.get("attributes") or {} for feature in features or [])
            if attrs.get(JURISDICTION_CODE_FIELD) and attrs.get(JURISDICTION_NAME_FIELD)
        }
        if not pairs:
            raise RuntimeError("NIFC jurisdiction layer returned no code/name pairs — nothing written")
        return pairs

    def _unit_name_map(self, codes: set[str]) -> dict[str, str]:
        """Names for *codes*, refreshing the lookup when it is missing or stale.

        Args:
            codes: Unit codes seen in the records; blank codes are ignored.

        Returns:
            ``code → name`` for every code the lookup resolves; unknown codes
            are absent and the caller falls back to the raw code.

        Raises:
            RuntimeError: When a refresh is needed and the layer fetch fails.
        """
        wanted = {code.strip() for code in codes if code and code.strip()}
        names = self._load_unit_names()
        if wanted - names.keys():
            names = _name_by_code(self._fetch_pairs())
            self._write_unit_names(names)
        return {code: names[code] for code in sorted(wanted & names.keys())}

    def _resolve_unit_names(self, records: list[dict]) -> None:
        """Stamp ``unit_name`` onto every record of a download.

        A known code resolves to its full name (``WAOWF`` → ``Okanogan-Wenatchee
        National Forest``), an unknown one keeps its raw value, a blank
        ``jurisdiction_label`` becomes an empty string — the same result the ETL
        used to compute from its own lookup. Does nothing for an empty batch.
        """
        if not records:
            return
        codes = {str(record.get("jurisdiction_label") or "") for record in records}
        wanted = {code.strip() for code in codes if code.strip()}
        names = self._unit_name_map(codes)
        for record in records:
            code = str(record.get("jurisdiction_label") or "").strip()
            record["unit_name"] = names.get(code, code) if code else ""
        self.logger.info(f"  unit-name lookup resolved {len(names)} of {len(wanted)} distinct codes")

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download current wildland fire perimeters from NIFC for the given date range.

        Queries the WFIGS feature service for fires active during the date range.
        Polygon geometry is NOT requested — only the attribute fields used by
        _build_record plus the feature centroid, which keeps the response small.
        The jurisdiction ``unit_name`` of every record is resolved from the
        unit-name lookup before the batch is returned.
        """
        self.logger.info(f"Downloading NIFC fire perimeter data for {start_date.date()} to {end_date.date()}")

        where_clause = (
            f"poly_DateCurrent >= TIMESTAMP '{self._format_datetime(start_date)}'"
            f" AND poly_DateCurrent <= TIMESTAMP '{self._format_datetime(end_date)}'"
        )

        params = {
            "where": where_clause,
            "outFields": ",".join(self._OUT_FIELDS),
            "returnGeometry": "false",
            "returnCentroid": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": 2000,
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base_url}?{query_string}"

        data = self._get_json(url)
        if not isinstance(data, dict):
            self.logger.warning("No data received from NIFC API")
            return []

        if "error" in data:
            self.logger.error(f"NIFC API rejected the query: {self._api_error_message(data)}")
            return []

        features = self._extract_features(data)
        self.logger.info(f"Received {len(features)} fire perimeter features")

        all_records: list[dict] = []
        for feature in features:
            record = self._build_record(feature)
            all_records.append(record)

        self._resolve_unit_names(all_records)
        stamp_geocode(
            all_records,
            output=self.reverse_geocode_file,
            columns=("geocode_state",),
            fetch_filter=lambda record: not str(record.get("state") or "").strip(),
            logger=self.logger,
        )

        self.logger.info(f"Downloaded {len(all_records)} NIFC fire perimeter records total")
        return all_records
