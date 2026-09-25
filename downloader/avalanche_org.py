from __future__ import annotations

import datetime as dt

from downloader.base import BaseDownloader


class AvalancheOrgDownloader(BaseDownloader):
    """Downloads avalanche danger ratings from the Avalanche.org API.

    Covers 28 US avalanche centers with 82+ forecast zones.
    Returns daily danger ratings (1-5 scale) with zone metadata.
    """

    @staticmethod
    def _build_record(feature: dict) -> dict:
        """Extract a flat record dict from a GeoJSON feature."""
        props = feature.get("properties", {})
        warning = props.get("warning", {}) or {}

        return {
            "zone_id": feature.get("id", ""),
            "zone_name": props.get("name", ""),
            "center_id": props.get("center_id", ""),
            "center_name": props.get("center", ""),
            "state": props.get("state", ""),
            "danger_level": props.get("danger_level", ""),
            "danger_rating": props.get("danger", ""),
            "travel_advice": props.get("travel_advice", ""),
            "off_season": props.get("off_season", ""),
            "forecast_start": props.get("start_date", "") or "",
            "forecast_end": props.get("end_date", "") or "",
            "warning": warning.get("product", "") or "",
            "link": props.get("link", ""),
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download avalanche danger ratings for the given date range.

        Queries the map-layer endpoint for each day. Returns danger ratings
        for all US avalanche zones.
        """
        self.logger.info(f"Downloading Avalanche.org data for {start_date.date()} to {end_date.date()}")

        all_records: list[dict] = []

        current = start_date
        while current <= end_date:
            url = f"{base_url}?day={self._format_date(current)}"
            data = self._get_json(url)

            if data and isinstance(data, dict) and data.get("type") == "FeatureCollection":
                features = self._extract_features(data)
                for feature in features:
                    record = self._build_record(feature)
                    record["date"] = self._format_date(current)
                    all_records.append(record)

                self.logger.info(f"  {current.date()}: {len(features)} zones")

            current += dt.timedelta(days=1)

        self.logger.info(f"Downloaded {len(all_records)} Avalanche.org records total")
        return all_records
