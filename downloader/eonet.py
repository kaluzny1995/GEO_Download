from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class EONETDownloader(BaseDownloader):
    """Downloads natural event data from NASA EONET (Earth Observatory Natural Event Tracker).

    Covers wildfires, storms, floods, volcanoes, earthquakes, drought,
    landslides, sea ice, temperature extremes, and more.
    """

    def _build_record(self, event: dict) -> dict:
        """Extract a flat record dict from an EONET event."""
        categories = event.get("categories", [])
        sources = event.get("sources", [])
        geometries = event.get("geometry", [])

        first_geom = geometries[0] if geometries else {}
        last_geom = geometries[-1] if geometries else {}

        first_lat, first_lon = self._extract_coords(first_geom)
        last_lat, last_lon = self._extract_coords(last_geom)

        return {
            "event_id": event.get("id", ""),
            "event_name": event.get("title", ""),
            "category_id": categories[0].get("id", "") if categories else "",
            "category_name": categories[0].get("title", "") if categories else "",
            "description": event.get("description", "") or "",
            "source_id": sources[0].get("id", "") if sources else "",
            "source_url": sources[0].get("url", "") if sources else "",
            "latitude": first_lat,
            "longitude": first_lon,
            "event_date": first_geom.get("date", ""),
            "magnitude_value": first_geom.get("magnitudeValue") or "",
            "magnitude_unit": first_geom.get("magnitudeUnit") or "",
            "closed": event.get("closed", "") or "",
            "geometry_count": len(geometries),
            "last_latitude": last_lat,
            "last_longitude": last_lon,
            "last_date": last_geom.get("date", ""),
        }

    @staticmethod
    def _extract_coords(geom: dict) -> tuple:
        """Extract (latitude, longitude) from a geometry dict.

        Handles Point ([lon, lat]) and Polygon ([[[lon, lat], ...]]) formats.
        Returns ("", "") if coordinates cannot be extracted.
        """
        coords = geom.get("coordinates")
        if not coords:
            return ("", "")

        geom_type = geom.get("type", "")

        if geom_type == "Polygon" and coords and coords[0]:
            point = coords[0][0]
            return (point[1], point[0]) if len(point) > 1 else ("", "")

        if isinstance(coords, list) and len(coords) >= 2:
            return (coords[1], coords[0])

        return ("", "")

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download natural events from NASA EONET for the given date range.

        Filters by event start date (start/end params).
        """
        self.logger.info(f"Downloading EONET events for {start_date.date()} to {end_date.date()}")

        url = (
            f"{base_url}"
            f"?start={self._format_date(start_date)}"
            f"&end={self._format_date(end_date)}"
        )

        data = self._get_json(url)
        data = self._validate_dict_response(data, "EONET")
        if not data:
            return []

        events = data.get("events", [])
        self.logger.info(f"Downloaded {len(events)} EONET events")

        return [self._build_record(event) for event in events]
