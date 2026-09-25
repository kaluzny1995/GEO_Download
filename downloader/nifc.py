from __future__ import annotations

import datetime as dt

from downloader.base import BaseDownloader


class NIFCDownloader(BaseDownloader):
    """Downloads current wildland fire perimeter data from NIFC ArcGIS REST services.

    Uses the WFIGS (Wildland Fire Interagency Geospatial Services) feature service
    to get current interagency fire perimeters for the United States.
    """

    @staticmethod
    def _build_record(feature: dict) -> dict:
        """Extract a flat record dict from an ArcGIS feature."""
        attrs = feature.get("attributes", {})

        return {
            "incident_name": attrs.get("poly_IncidentName", ""),
            "irwin_id": attrs.get("poly_IRWINID", ""),
            "fire_number": attrs.get("poly_FireDiscoveryDateTime", ""),
            "acres": attrs.get("poly_GIS Acres", ""),
            "percent_contained": attrs.get("poly_PercentContained", ""),
            "fire_type": attrs.get("poly_FireType", ""),
            "fire_type_label": attrs.get("poly_FireType_LABEL", ""),
            "jurisdiction": attrs.get("poly_Jurisdiction", ""),
            "jurisdiction_label": attrs.get("poly_Jurisdiction_LABEL", ""),
            "state": attrs.get("poly_State", ""),
            "po_method": attrs.get("poly_POOState", ""),
            "latitude": attrs.get("poly_Latitude", ""),
            "longitude": attrs.get("poly_longitude", ""),
            "poly_date": attrs.get("poly_DateCurrent", ""),
            "created_on": attrs.get("attr_CreatedOnDateTime_dt", ""),
            "modified_on": attrs.get("attr_ModifiedOnDateTime_dt", ""),
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download current wildland fire perimeters from NIFC for the given date range.

        Queries the WFIGS feature service for fires active during the date range.
        Geometry is NOT requested — only the specific attribute fields used by
        _build_record are fetched, which dramatically reduces response size.
        """
        self.logger.info(f"Downloading NIFC fire perimeter data for {start_date.date()} to {end_date.date()}")

        where_clause = (
            f"poly_DateCurrent >= TIMESTAMP '{self._format_datetime(start_date)}'"
            f" AND poly_DateCurrent <= TIMESTAMP '{self._format_datetime(end_date)}'"
        )

        params = {
            "where": where_clause,
            "outFields": ",".join([
                "poly_IncidentName",
                "poly_IRWINID",
                "poly_FireDiscoveryDateTime",
                "poly_GIS Acres",
                "poly_PercentContained",
                "poly_FireType",
                "poly_FireType_LABEL",
                "poly_Jurisdiction",
                "poly_Jurisdiction_LABEL",
                "poly_State",
                "poly_POOState",
                "poly_Latitude",
                "poly_longitude",
                "poly_DateCurrent",
                "attr_CreatedOnDateTime_dt",
                "attr_ModifiedOnDateTime_dt",
            ]),
            "returnGeometry": "false",
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

        features = self._extract_features(data)
        self.logger.info(f"Received {len(features)} fire perimeter features")

        all_records: list[dict] = []
        for feature in features:
            record = self._build_record(feature)
            all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} NIFC fire perimeter records total")
        return all_records
