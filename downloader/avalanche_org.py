from __future__ import annotations

import csv
import datetime as dt
import logging
import os
from itertools import pairwise
from pathlib import Path
from typing import ClassVar

from downloader.base import BaseDownloader


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    """Centroid and area of one closed GeoJSON ring of ``[lon, lat]`` vertices.

    A degenerate ring falls back to its vertex average with an area of ``0``.
    """
    area = 0.0
    lon = 0.0
    lat = 0.0
    for (x0, y0), (x1, y1) in pairwise(ring):
        cross = x0 * y1 - x1 * y0
        area += cross
        lon += (x0 + x1) * cross
        lat += (y0 + y1) * cross
    area *= 0.5
    if abs(area) < 1e-12 or len(ring) < 2:
        points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
        lons = [point[0] for point in points] or [0.0]
        lats = [point[1] for point in points] or [0.0]
        return sum(lons) / len(lons), sum(lats) / len(lats), 0.0
    return lon / (6 * area), lat / (6 * area), abs(area)


def _polygon_centroid(rings: list[list[list[float]]]) -> tuple[float, float, float]:
    """Area weighted centroid of a GeoJSON polygon: exterior ring minus its holes.

    Falls back to the exterior ring when the holes cancel out the whole area.
    """
    ext_lon, ext_lat, ext_area = _ring_centroid(rings[0])
    lon, lat, total = ext_lon * ext_area, ext_lat * ext_area, ext_area
    for hole in rings[1:]:
        hole_lon, hole_lat, hole_area = _ring_centroid(hole)
        lon -= hole_lon * hole_area
        lat -= hole_lat * hole_area
        total -= hole_area
    if total <= 0:
        return ext_lon, ext_lat, ext_area
    return lon / total, lat / total, total


def _geometry_centroid(geometry: dict | None) -> tuple[float, float] | None:
    """Centroid of a GeoJSON ``Polygon`` or ``MultiPolygon``.

    Returns ``(lon, lat)``, or ``None`` when the geometry is missing or empty.
    """
    if not geometry:
        return None
    gtype = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if gtype == "Polygon":
        polygons = [coordinates]
    elif gtype == "MultiPolygon":
        polygons = coordinates
    else:
        return None
    lon = 0.0
    lat = 0.0
    total = 0.0
    for polygon in polygons:
        if not polygon:
            continue
        poly_lon, poly_lat, area = _polygon_centroid(polygon)
        lon += poly_lon * area
        lat += poly_lat * area
        total += area
    if total <= 0:
        return None
    return lon / total, lat / total


class AvalancheOrgDownloader(BaseDownloader):
    """Downloads avalanche danger ratings from the Avalanche.org API.

    Covers 28 US avalanche centers with 82+ forecast zones.
    Returns daily danger ratings (1-5 scale) with zone metadata and the zone
    polygon centroid (``latitude``/``longitude``). The centroids are also
    merged into the consolidated lookup ``data/avalanche_org_notices.csv``
    (``place_location, state, latitude, longitude``), keyed zone name + state,
    so zones that leave the feed stay covered.
    """

    DEFAULT_NOTICES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "avalanche_org_notices.csv")
    NOTICES_FIELDS: ClassVar[list[str]] = ["place_location", "state", "latitude", "longitude"]
    notices_file: str | None = None

    def __init__(
        self,
        timeout: int = 30,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        notices_file: str | None = None,
    ):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self.notices_file = notices_file or self.DEFAULT_NOTICES_FILE

    @staticmethod
    def _build_record(feature: dict) -> dict:
        """Extract a flat record dict from a GeoJSON feature.

        ``latitude``/``longitude`` are the area weighted centroid of the zone
        polygon, rounded to 6 decimals; a feature without usable geometry gets
        empty values.
        """
        props = feature.get("properties", {})
        warning = props.get("warning", {}) or {}
        centroid = _geometry_centroid(feature.get("geometry"))

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
            "latitude": round(centroid[1], 6) if centroid else "",
            "longitude": round(centroid[0], 6) if centroid else "",
        }

    def _update_notices(self, records: list[dict]) -> None:
        """Merge the day's zone centroids into the notices lookup CSV.

        Existing rows are kept (zones come and go — a zone absent from today's
        feed stays covered), rows of zones seen again are refreshed, and the
        result is sorted by state and zone name. Records without coordinates
        are skipped. Does nothing when no lookup path is configured.
        """
        if not self.notices_file or not records:
            return

        zones: dict[tuple[str, str], dict] = {}
        if os.path.exists(self.notices_file):
            with open(self.notices_file, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    name = (row.get("place_location") or "").strip()
                    if name:
                        zones[(name, (row.get("state") or "").strip())] = {
                            "place_location": name,
                            "state": (row.get("state") or "").strip(),
                            "latitude": row.get("latitude", ""),
                            "longitude": row.get("longitude", ""),
                        }

        for record in records:
            name = str(record.get("zone_name") or "").strip()
            state = str(record.get("state") or "").strip()
            latitude = record.get("latitude")
            longitude = record.get("longitude")
            if not name or latitude in ("", None) or longitude in ("", None):
                continue
            zones[(name, state)] = {
                "place_location": name,
                "state": state,
                "latitude": latitude,
                "longitude": longitude,
            }

        if not zones:
            return

        os.makedirs(os.path.dirname(self.notices_file) or ".", exist_ok=True)
        with open(self.notices_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.NOTICES_FIELDS)
            writer.writeheader()
            writer.writerows(sorted(zones.values(), key=lambda row: (row["state"], row["place_location"])))
        self.logger.info(f"  notices lookup: {len(zones)} zones -> {self.notices_file}")

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download avalanche danger ratings for the given date range.

        Queries the map-layer endpoint for each day. Returns danger ratings
        for all US avalanche zones and refreshes the notices lookup with the
        centroids seen along the way.
        """
        self.logger.info(f"Downloading Avalanche.org data for {start_date.date()} to {end_date.date()}")

        all_records: list[dict] = []

        current = start_date
        while current <= end_date:
            url = f"{base_url}?day={self._format_date(current)}"
            data = self._get_json(url)

            if data and isinstance(data, dict) and data.get("type") == "FeatureCollection":
                features = self._extract_features(data)
                day_records = []
                for feature in features:
                    record = self._build_record(feature)
                    record["date"] = self._format_date(current)
                    day_records.append(record)
                all_records.extend(day_records)

                self.logger.info(f"  {current.date()}: {len(features)} zones")
                self._update_notices(day_records)

            current += dt.timedelta(days=1)

        self.logger.info(f"Downloaded {len(all_records)} Avalanche.org records total")
        return all_records
