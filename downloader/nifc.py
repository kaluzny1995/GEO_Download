from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class NIFCDownloader(BaseDownloader):
    """Downloads current wildland fire perimeter data from NIFC ArcGIS REST services.

    Uses the WFIGS (Wildland Fire Interagency Geospatial Services) feature service
    to get current interagency fire perimeters for the United States.
    """

    def _build_record(self, feature: dict) -> dict:
        """Extract a flat record dict from an ArcGIS feature."""
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry", {})

        rings = geom.get("rings", [[]])
        if rings and rings[0]:
            first_ring = rings[0]
            centroid_lon = sum(p[0] for p in first_ring) / len(first_ring)
            centroid_lat = sum(p[1] for p in first_ring) / len(first_ring)
        else:
            centroid_lon = ""
            centroid_lat = ""

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
            "latitude": centroid_lat,
            "longitude": centroid_lon,
            "poly_date": attrs.get("poly_DateCurrent", ""),
            "created_on": attrs.get("attr_CreatedOnDateTime_dt", ""),
            "modified_on": attrs.get("attr_ModifiedOnDateTime_dt", ""),
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download current wildland fire perimeters from NIFC for the given date range.

        Queries the WFIGS feature service for fires active during the date range.
        """
        self.logger.info(f"Downloading NIFC fire perimeter data for {start_date.date()} to {end_date.date()}")

        where_clause = f"poly_DateCurrent >= TIMESTAMP '{self._format_datetime(start_date)}' AND poly_DateCurrent <= TIMESTAMP '{self._format_datetime(end_date)}'"

        params = {
            "where": where_clause,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": 2000,
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base_url}?{query_string}"

        data = self._get_json(url)
        data = self._validate_dict_response(data, "NIFC")
        if not data:
            return []

        features = self._extract_features(data)
        self.logger.info(f"Received {len(features)} fire perimeter features")

        all_records: list[dict] = []
        for feature in features:
            record = self._build_record(feature)
            all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} NIFC fire perimeter records total")
        return all_records
