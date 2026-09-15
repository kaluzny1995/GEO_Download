from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class USGSVolcanoDownloader(BaseDownloader):
    """Downloads volcano alert data from the USGS HANS API."""

    __slots__ = ("_volcano_cache", "_name_to_code")

    BASE_URL = "https://volcanoes.usgs.gov/hans-public/api"

    def __init__(self, timeout: int = 30, logger=None, log_folder: str | None = None):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._volcano_cache: dict = {}
        self._name_to_code: dict = {}

    def _load_volcano_cache(self) -> None:
        """Pre-load all US volcanoes for name-to-code lookup and enrichment."""
        if self._volcano_cache:
            return

        data = self._get_json(f"{self.BASE_URL}/volcano/getUSVolcanoes")
        if data:
            for v in data:
                code = v.get("volcano_cd", "")
                self._volcano_cache[code] = v
                self._name_to_code[v.get("volcano_name", "")] = code
            self.logger.info(f"Loaded {len(self._volcano_cache)} volcanoes into cache")

    def _get_volcano_codes_from_names(self, names_csv: str) -> list[str]:
        """Resolve comma-separated volcano names to codes."""
        codes = []
        for name in names_csv.split(","):
            name = name.strip()
            if name in self._name_to_code:
                codes.append(self._name_to_code[name])
            else:
                self.logger.warning(f"No code found for volcano name: {name}")
        return codes

    def _get_notice_parts(self, notice_identifier: str) -> dict:
        """Get structured parts of a notice."""
        data = self._get_json(f"{self.BASE_URL}/notice/getNoticeParts/{notice_identifier}")
        if data and isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _parse_sent_date(sent_utc: str) -> dt.date | None:
        """Parse sent_utc string to date."""
        try:
            return dt.datetime.strptime(sent_utc[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def _build_record(self, notice: dict, volcano_cd: str, sent_date: dt.date,
                      alert_level: str = "", color_code: str = "",
                      notice_summary: str = "", notice_number: str = "") -> dict:
        """Build a single record dict from notice and volcano data."""
        volcano_info = self._volcano_cache.get(volcano_cd, {})
        return {
            "country_code": "US",
            "observatory_code": notice.get("obs_abbr", ""),
            "observatory_name": notice.get("obs_fullname", ""),
            "volcano_code": volcano_cd,
            "volcano_name": volcano_info.get("volcano_name", ""),
            "latitude": volcano_info.get("latitude", ""),
            "longitude": volcano_info.get("longitude", ""),
            "elevation_meters": volcano_info.get("elevation_meters", ""),
            "region": volcano_info.get("region", ""),
            "vnum": volcano_info.get("vnum", ""),
            "nvews_threat": volcano_info.get("nvews_threat", ""),
            "notice_identifier": notice.get("notice_identifier", ""),
            "notice_type": notice.get("notice_type_title", ""),
            "notice_type_cd": notice.get("notice_type_cd", ""),
            "notice_category": notice.get("notice_category", ""),
            "notice_url": notice.get("notice_url", ""),
            "sent_utc": notice.get("sent_utc", ""),
            "sent_date": sent_date.isoformat() if sent_date else "",
            "alert_level": alert_level,
            "color_code": color_code,
            "notice_summary": notice_summary,
            "notice_number": notice_number,
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download volcano alert data for a specific date range.

        The base_url is ignored; the HANS API is used directly.
        """
        start = start_date.date()
        end = end_date.date()

        self.logger.info(f"Downloading volcano alerts for period: {start} to {end}")

        self._load_volcano_cache()

        notices = self._get_json(f"{self.BASE_URL}/notice/getRecentNotices")
        if not notices:
            self.logger.warning("No notices retrieved")
            return []

        self.logger.info(f"Retrieved {len(notices)} total notices")

        records = []
        for notice in notices:
            sent_date = self._parse_sent_date(notice.get("sent_utc", ""))
            if sent_date is None:
                continue
            if not (start <= sent_date < end):
                continue

            notice_id = notice.get("notice_identifier", "")
            volcano_names = notice.get("volcanoes", "")

            parts = self._get_notice_parts(notice_id)
            sections = parts.get("sections", []) if parts else []

            if sections:
                for section in sections:
                    volcano_cd = section.get("volcano_cd", "")
                    record = self._build_record(
                        notice, volcano_cd, sent_date,
                        alert_level=section.get("alert_level", ""),
                        color_code=section.get("color_code", ""),
                        notice_summary=section.get("synopsis", ""),
                        notice_number=section.get("notice_number", ""),
                    )
                    records.append(record)
            else:
                volcano_cds = self._get_volcano_codes_from_names(volcano_names)
                for volcano_cd in volcano_cds:
                    record = self._build_record(notice, volcano_cd, sent_date)
                    records.append(record)

        self.logger.info(f"Downloaded {len(records)} volcano alert records")
        return records
