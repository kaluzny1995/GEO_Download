from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class NIFCDownloader(BaseDownloader):
    """Downloads current wildland fire perimeter data from NIFC ArcGIS REST services.

    Uses the WFIGS (Wildland Fire Interagency Geospatial Services) feature service
    to get current interagency fire perimeters for the United States.
    """

    WFIGS_PERIMETERS_URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"

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

        poly_date = attrs.get("poly_GIS Acres", "")
        fire_size = attrs.get("poly_IncidentName", "")

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

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        where_clause = f"poly_DateCurrent >= TIMESTAMP '{start_date.strftime('%Y-%m-%d %H:%M:%S')}' AND poly_DateCurrent <= TIMESTAMP '{end_date.strftime('%Y-%m-%d %H:%M:%S')}'"

        params = {
            "where": where_clause,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": 2000,
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.WFIGS_PERIMETERS_URL}?{query_string}"

        data = self._get_json(url)

        if not data or not isinstance(data, dict):
            self.logger.warning("No data received from NIFC API")
            return []

        features = data.get("features", [])
        self.logger.info(f"Received {len(features)} fire perimeter features")

        all_records: list[dict] = []
        for feature in features:
            record = self._build_record(feature)
            all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} NIFC fire perimeter records total")
        return all_records
