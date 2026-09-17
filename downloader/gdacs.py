from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class GDACSDownloader(BaseDownloader):
    """Downloads global natural disaster data from the GDACS API.

    Covers earthquakes (EQ), tropical cyclones (TC), floods (FL),
    volcanoes (VO), wildfires (WF), and droughts (DR).
    """

    __slots__ = ("_event_types", "_page_size")

    def __init__(self, timeout: int = 30, logger=None, log_folder: str | None = None,
                 event_types: str = "EQ;TC;FL;VO;WF;DR", page_size: int = 100):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._event_types = event_types
        self._page_size = page_size

    def _build_record(self, feature: dict) -> dict:
        """Extract a flat record dict from a GeoJSON feature."""
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [None, None]) if geom else [None, None]
        severity_data = props.get("severitydata", {}) or {}

        return {
            "event_type": props.get("eventtype", ""),
            "event_id": props.get("eventid", ""),
            "event_name": props.get("name", ""),
            "alert_level": props.get("alertlevel", ""),
            "country": props.get("country", ""),
            "country_code": props.get("iso3", ""),
            "latitude": coords[1] if len(coords) > 1 else "",
            "longitude": coords[0] if len(coords) > 0 else "",
            "from_date": props.get("fromdate", ""),
            "to_date": props.get("todate", ""),
            "date_modified": props.get("datemodified", ""),
            "severity": severity_data.get("severity", ""),
            "severity_text": severity_data.get("severitytext", ""),
            "severity_unit": severity_data.get("severityunit", ""),
            "source": props.get("source", ""),
            "report_url": (props.get("url") or {}).get("report", ""),
            "is_current": props.get("iscurrent", ""),
        }

    def _fetch_page(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime, page: int) -> list[dict]:
        """Fetch a single page of GDACS events."""
        params = (
            f"?eventlist={self._event_types}"
            f"&fromdate={self._format_date(start_date)}"
            f"&todate={self._format_date(end_date)}"
            f"&alertlevel=red;orange;green"
            f"&pagesize={self._page_size}"
            f"&pagenumber={page}"
        )
        url = f"{base_url}{params}"
        data = self._get_json(url)
        if not data or not isinstance(data, dict):
            return []
        return self._extract_features(data)

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download disaster events from GDACS for the given date range.

        Handles pagination to retrieve all events (100 per page).
        """
        self.logger.info(f"Downloading GDACS events for {start_date.date()} to {end_date.date()}")

        all_records: list[dict] = []
        page = 1

        while True:
            features = self._fetch_page(base_url, start_date, end_date, page)
            if not features:
                break

            for feature in features:
                record = self._build_record(feature)
                all_records.append(record)

            self.logger.info(f"  Page {page}: {len(features)} events")

            if len(features) < self._page_size:
                break
            page += 1

        self.logger.info(f"Downloaded {len(all_records)} GDACS events total")
        return all_records
