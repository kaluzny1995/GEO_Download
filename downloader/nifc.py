from __future__ import annotations

import datetime as dt
from typing import ClassVar

from downloader.base import BaseDownloader


def _state_code(poo_state: str) -> str:
    """Convert an IRWIN point-of-origin state value ('US-CO') to a bare code ('CO')."""
    if poo_state.startswith("US-"):
        return poo_state[3:]
    return poo_state


def _attr(attrs: dict, key: str) -> str | float | int:
    """Read an ArcGIS attribute, mapping null values to an empty string."""
    value = attrs.get(key)
    return "" if value is None else value


class NIFCDownloader(BaseDownloader):
    """Downloads current wildland fire perimeter data from NIFC ArcGIS REST services.

    Uses the WFIGS (Wildland Fire Interagency Geospatial Services) feature service
    to get current interagency fire perimeters for the United States.

    Field naming on that layer: ``poly_*`` are perimeter-level attributes and
    ``attr_*`` are incident attributes mirrored onto every perimeter. Every name in
    :attr:`_OUT_FIELDS` must exist on the layer — ArcGIS rejects unknown
    ``outFields`` with an HTTP 200 body carrying ``{"error": …}`` rather than a
    non-2xx status, so a stale name fails silently instead of raising.
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

    @staticmethod
    def _build_record(feature: dict) -> dict:
        """Extract a flat record dict from an ArcGIS feature.

        Coordinates come from the feature centroid (requested via
        ``returnCentroid=true``), falling back to the incident's point of origin
        when the service omits it.
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

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download current wildland fire perimeters from NIFC for the given date range.

        Queries the WFIGS feature service for fires active during the date range.
        Polygon geometry is NOT requested — only the attribute fields used by
        _build_record plus the feature centroid, which keeps the response small.
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

        self.logger.info(f"Downloaded {len(all_records)} NIFC fire perimeter records total")
        return all_records
