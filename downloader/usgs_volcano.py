from __future__ import annotations
import datetime as dt

from downloader.base import BaseDownloader


class USGSVolcanoDownloader(BaseDownloader):
    """Downloads volcano alert data from the USGS Volcano Hazards Program API.

    Uses the HANS API to get volcanoes with elevated alert levels (Yellow, Orange, Red).
    Only volcanoes above NORMAL/GREEN status are included — these are the
    time-varying entries that change day to day as conditions evolve.

    Covers US-monitored volcanoes across observatories:
    Alaska (AVO), California (CALVO), Cascades (CVO), Hawaiian (HVO),
    Northern Mariana Islands (NMI), and Yellowstone (YVO).
    """

    ELEVATED_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes"

    def _build_record(self, volcano: dict) -> dict:
        """Extract a flat record dict from a volcano status entry."""
        return {
            "volcano_name": volcano.get("volcano_name", ""),
            "vnum": volcano.get("vnum", ""),
            "observatory": volcano.get("obs_abbr", ""),
            "observatory_name": volcano.get("obs_fullname", ""),
            "alert_level": volcano.get("alert_level", ""),
            "color_code": volcano.get("color_code", ""),
            "notice_type": volcano.get("notice_type_cd", ""),
            "notice_identifier": volcano.get("notice_identifier", ""),
            "notice_date": volcano.get("sent_utc", ""),
            "notice_url": volcano.get("notice_url", ""),
            "notice_data_url": volcano.get("notice_data", ""),
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download elevated volcano alerts from USGS HANS API for the given date range.

        Only returns volcanoes with alert level above NORMAL (i.e. ADVISORY, WATCH, WARNING).
        Filters by notice_date to include only notices issued within the date range.
        """
        self.logger.info(f"Downloading USGS Volcano data for {start_date.date()} to {end_date.date()}")

        data = self._get_json(self.ELEVATED_URL)

        if not data or not isinstance(data, list):
            self.logger.warning("No data received from USGS Volcano API")
            return []

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        all_records: list[dict] = []
        for volcano in data:
            record = self._build_record(volcano)
            notice_date = record.get("notice_date", "")
            if notice_date and start_str <= notice_date[:10] <= end_str:
                all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} USGS Volcano records total")
        return all_records
