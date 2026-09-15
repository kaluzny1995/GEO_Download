from __future__ import annotations
import datetime as dt
import json
import os
import time

from downloader.base import BaseDownloader


class SmithsonianGVPDownloader(BaseDownloader):
    """Downloads worldwide volcano data from the Smithsonian Global Volcanism Program.

    Uses the volcview API (USGS) for volcano list and BigDataCloud for country code enrichment.
    """

    __slots__ = ("_volcano_cache", "_country_cache", "_cache_file")

    VOLCVIEW_URL = "https://volcview.wr.usgs.gov/vv-api/volcanoApi/wwvolcanoes"
    GEOCODE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"
    CACHE_FILE = "data/.volcano_country_cache.json"

    def __init__(self, timeout: int = 30, logger=None, log_folder: str | None = None):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._volcano_cache: list[dict] = []
        self._country_cache: dict[str, dict] = {}
        self._cache_file = self.CACHE_FILE
        self._load_country_cache()

    def _load_country_cache(self) -> None:
        """Load country code cache from local file."""
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    self._country_cache = json.load(f)
                self.logger.info(f"Loaded {len(self._country_cache)} cached country lookups")
            except Exception as e:
                self.logger.warning(f"Failed to load country cache: {e}")
                self._country_cache = {}

    def _save_country_cache(self) -> None:
        """Save country code cache to local file."""
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._country_cache, f, indent=2)
            self.logger.info(f"Saved {len(self._country_cache)} country lookups to cache")
        except Exception as e:
            self.logger.error(f"Failed to save country cache: {e}")

    def _get_country_code(self, lat: float, lon: float) -> dict:
        """Get country code and name for coordinates, using cache when available."""
        cache_key = f"{lat:.4f},{lon:.4f}"
        if cache_key in self._country_cache:
            return self._country_cache[cache_key]

        try:
            params = {"latitude": lat, "longitude": lon, "localityLanguage": "en"}
            response = self.session.get(self.GEOCODE_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            result = {
                "country_code": data.get("countryCode", ""),
                "country_name": data.get("countryName", ""),
            }
            self._country_cache[cache_key] = result
            return result
        except Exception as e:
            self.logger.error(f"Failed to geocode ({lat}, {lon}): {e}")
            return {"country_code": "", "country_name": ""}

    def _enrich_volcanoes_with_country(self, volcanoes: list[dict]) -> list[dict]:
        """Enrich volcano list with country codes from geocoding."""
        unique_coords: dict[str, dict] = {}
        for v in volcanoes:
            lat = v.get("lat", 0)
            lon = v.get("lng", 0)
            key = f"{lat:.4f},{lon:.4f}"
            if key not in unique_coords:
                unique_coords[key] = {"lat": lat, "lon": lon}

        uncached = [k for k, v in unique_coords.items() if k not in self._country_cache]
        if uncached:
            self.logger.info(f"Geocoding {len(uncached)} unique coordinates...")
            for i, key in enumerate(uncached):
                lat, lon = unique_coords[key]["lat"], unique_coords[key]["lon"]
                self._get_country_code(lat, lon)
                if (i + 1) % 50 == 0:
                    self.logger.info(f"  Geocoded {i + 1}/{len(uncached)}")
                time.sleep(0.05)  # Rate limit: ~20 req/s
            self._save_country_cache()

        enriched = []
        for v in volcanoes:
            lat = v.get("lat", 0)
            lon = v.get("lng", 0)
            cache_key = f"{lat:.4f},{lon:.4f}"
            geo = self._country_cache.get(cache_key, {"country_code": "", "country_name": ""})
            enriched.append({
                "vnum": v.get("vnum", ""),
                "volcano_name": v.get("vn", ""),
                "latitude": lat,
                "longitude": lon,
                "elevation_meters": v.get("elevM", ""),
                "observatory_code": v.get("obsAbbr", ""),
                "country_code": geo["country_code"],
                "country_name": geo["country_name"],
            })

        self.logger.info(f"Enriched {len(enriched)} volcanoes with country codes")
        return enriched

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download worldwide volcano data from the Smithsonian GVP via volcview.

        The base_url is ignored; the volcview API is used directly.
        Returns all volcanoes with country codes enriched via geocoding.
        """
        self.logger.info("Downloading worldwide volcano data from Smithsonian GVP (volcview)")

        data = self._get_json(self.VOLCVIEW_URL)
        if not data or not isinstance(data, list):
            self.logger.warning("No volcano data retrieved from volcview")
            return []

        self.logger.info(f"Retrieved {len(data)} volcanoes from volcview")
        self._volcano_cache = data

        enriched = self._enrich_volcanoes_with_country(data)
        return enriched
