from __future__ import annotations

import csv
import datetime as dt
import logging
import os
from itertools import pairwise
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlencode

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
    Returns daily danger ratings (1-5 scale) with zone metadata, the zone
    polygon centroid (``latitude``/``longitude``) and the expected avalanche
    size (``avalanche_size`` - destructive size class D1-D5, read from the
    per-zone forecast product). The centroids are also
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
        empty values. ``avalanche_size`` starts empty and is filled by
        :meth:`_zone_size` from the zone's forecast product when one is
        available for the day.
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
            "avalanche_size": "",
        }

    @staticmethod
    def _forecast_url(base_url: str) -> str:
        """The per-zone forecast endpoint sitting beside the map-layer one.

        The public API docs only describe ``/v2/public/products/map-layer``;
        the full forecast (avalanche problems, expected sizes) is served by
        the sibling ``/v2/public/product`` route, derived here so the
        configured ``api_url`` stays the single source of truth.
        """
        return base_url.replace("/products/map-layer", "/product")

    @staticmethod
    def _avalanche_size(product: dict | None) -> str:
        """Largest expected destructive size class (D1-D5) of a forecast product.

        Every entry of ``forecast_avalanche_problems`` carries a ``size``
        array of per-elevation-band classes (``"2"``, ``"2.5"`` …); the
        largest one wins and is rendered without trailing zeros (``3``,
        ``2.5``). Centers publish half steps (D1.5 … D4.5), so the answer is
        not restricted to whole classes.

        Returns:
            The size class as text, or ``""`` when the product publishes no
            problems (off-season statements, early season) or none of the
            sizes parse as a number.
        """
        sizes: list[float] = []
        for problem in (product or {}).get("forecast_avalanche_problems") or []:
            for value in problem.get("size") or []:
                try:
                    sizes.append(float(value))
                except (TypeError, ValueError):
                    continue
        return "" if not sizes else f"{max(sizes):g}"

    @staticmethod
    def _product_covers_day(product: dict | None, day: dt.date) -> bool:
        """Whether the *current-only* forecast product is valid on *day*.

        The forecast endpoint ignores a ``day`` parameter — it always serves
        the live product — so its size may only be attached to a day inside
        the product's own publish/expiry window. A historic backfill of past
        CSVs then leaves the sizes empty instead of stamping today's answer
        onto a past day.

        Returns:
            ``True`` when ``published_time`` ≤ *day* ≤ ``expires_time``;
            ``False`` for a missing product or unreadable timestamps.
        """
        if not product:
            return False
        try:
            start = dt.datetime.fromisoformat(product["published_time"]).date()
            end = dt.datetime.fromisoformat(product["expires_time"]).date()
        except (KeyError, TypeError, ValueError):
            return False
        return start <= day <= end

    def _zone_size(self, feature: dict, forecast_url: str, day: dt.date, cache: dict) -> str:
        """The zone's expected size class on *day*, fetched at most once per zone.

        Only rated zones (``danger_level`` ≥ 1) are looked up — an unrated or
        off-season zone has no problems to size — and the product is cached
        per ``(center_id, zone_id)`` so a multi-day range does not refetch it.

        Args:
            feature: The map-layer GeoJSON feature of the zone.
            forecast_url: The per-zone forecast endpoint (:meth:`_forecast_url`).
            day: The map-layer day being downloaded.
            cache: Caller-owned ``(center_id, zone_id)`` → product map.

        Returns:
            The size class as text, or ``""`` when the zone is unrated, the
            product is missing or it does not cover *day*.
        """
        props = feature.get("properties") or {}
        level = props.get("danger_level")
        if not isinstance(level, int) or isinstance(level, bool) or level < 1:
            return ""
        key = (str(props.get("center_id", "") or ""), feature.get("id"))
        if key not in cache:
            query = urlencode({"type": "forecast", "center_id": key[0], "zone_id": key[1]})
            cache[key] = self._get_json(f"{forecast_url}?{query}")
        product = cache[key]
        return self._avalanche_size(product) if self._product_covers_day(product, day) else ""

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

        Queries the map-layer endpoint for each day and, for every rated
        zone, the per-zone forecast endpoint for the expected avalanche size
        (``avalanche_size`` - the largest destructive size class D1-D5 the
        forecast publishes; empty off-season or for a day outside the live
        product's window). Returns danger ratings for all US avalanche zones
        and refreshes the notices lookup with the centroids seen along the
        way.
        """
        self.logger.info(f"Downloading Avalanche.org data for {start_date.date()} to {end_date.date()}")

        all_records: list[dict] = []
        forecast_url = self._forecast_url(base_url)
        products: dict[tuple[str, object], dict | None] = {}

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
                    record["avalanche_size"] = self._zone_size(feature, forecast_url, current.date(), products)
                    day_records.append(record)
                all_records.extend(day_records)

                self.logger.info(f"  {current.date()}: {len(features)} zones")
                self._update_notices(day_records)

            current += dt.timedelta(days=1)

        self.logger.info(f"Downloaded {len(all_records)} Avalanche.org records total")
        return all_records
