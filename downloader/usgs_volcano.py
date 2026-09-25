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

    @staticmethod
    def _build_record(volcano: dict) -> dict:
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

        url = f"{base_url}/getElevatedVolcanoes"
        data = self._get_json(url)
        data = self._validate_list_response(data, "USGS Volcano")
        if not data:
            return []

        start_str = self._format_date(start_date)
        end_str = self._format_date(end_date)

        all_records: list[dict] = []
        for volcano in data:
            record = self._build_record(volcano)
            notice_date = record.get("notice_date", "")
            if notice_date and start_str <= notice_date[:10] <= end_str:
                all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} USGS Volcano records total")
        return all_records
