from __future__ import annotations
import logging
import datetime as dt

from downloader.base import BaseDownloader


class USGSNWISDownloader(BaseDownloader):
    """Downloads daily streamflow data from the USGS NWIS WaterServices API.

    Queries daily discharge values (parameter code 00060, mean statistic 00003)
    from the USGS National Water Information System.
    """

    def __init__(self, timeout: int = 60, logger: logging.Logger | None = None,
                 log_folder: str | None = None,
                 sites: str = "01646500", parameter_code: str = "00060"):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self._sites = sites
        self._parameter_code = parameter_code

    def _build_url(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> str:
        """Build the API query URL."""
        params = [
            "format=json",
            f"sites={self._sites}",
            f"parameterCd={self._parameter_code}",
            f"startDT={self._format_date(start_date)}",
            f"endDT={self._format_date(end_date)}",
        ]
        return f"{base_url}?{'&'.join(params)}"

    def _build_record(self, time_series: dict, value_entry: dict, site_info: dict) -> dict:
        """Extract a flat record dict from a time series value."""
        site_code = site_info.get("siteCode", [{}])[0].get("value", "")
        site_name = site_info.get("siteName", "")
        geo = site_info.get("geoLocation", {}).get("geogLocation", {})
        lat = geo.get("latitude", "")
        lon = geo.get("longitude", "")

        variable = time_series.get("variable", {})
        var_code = variable.get("variableCode", [{}])[0].get("value", "")
        unit = variable.get("unit", {}).get("unitCode", "")

        return {
            "site_id": f"USGS-{site_code}",
            "site_name": site_name,
            "parameter_code": var_code,
            "date": value_entry.get("dateTime", "")[:10],
            "value": value_entry.get("value", ""),
            "unit": unit,
            "qualifiers": ",".join(value_entry.get("qualifiers", [])),
            "latitude": lat,
            "longitude": lon,
        }

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download daily discharge data from USGS NWIS for the given date range."""
        self.logger.info(f"Downloading USGS NWIS daily data for {start_date.date()} to {end_date.date()}")
        self.logger.info(f"  sites={self._sites}, parameter={self._parameter_code}")

        url = self._build_url(base_url, start_date, end_date)
        data = self._get_json(url)

        data = self._validate_dict_response(data, "USGS NWIS")
        if not data:
            return []

        time_series_list = data.get("value", {}).get("timeSeries", [])
        self.logger.info(f"Received {len(time_series_list)} time series")

        all_records: list[dict] = []
        for ts in time_series_list:
            site_info = ts.get("sourceInfo", {})
            values_list = ts.get("values", [{}])
            for values_obj in values_list:
                for value_entry in values_obj.get("value", []):
                    record = self._build_record(ts, value_entry, site_info)
                    all_records.append(record)

        self.logger.info(f"Downloaded {len(all_records)} USGS NWIS records total")
        return all_records
