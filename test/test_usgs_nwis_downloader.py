import pytest
import datetime as dt
from unittest.mock import patch, MagicMock

from downloader.usgs_nwis import USGSNWISDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))

    def warning(self, msg):
        self.messages.append(("WARNING", msg))


SAMPLE_API_RESPONSE = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "POTOMAC RIVER NEAR WASH, DC",
                    "siteCode": [{"value": "01646500", "network": "NWIS", "agencyCode": "USGS"}],
                    "geoLocation": {
                        "geogLocation": {"srs": "EPSG:4326", "latitude": 38.94977778, "longitude": -77.12763889}
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00060"}],
                    "variableName": "Streamflow, ft³/s",
                    "unit": {"unitCode": "ft3/s"},
                },
                "values": [{
                    "value": [
                        {"value": "2320", "qualifiers": ["P"], "dateTime": "2026-09-01T00:00:00.000"},
                        {"value": "2220", "qualifiers": ["P"], "dateTime": "2026-09-02T00:00:00.000"},
                    ],
                }],
            },
            {
                "sourceInfo": {
                    "siteName": "HUDSON RIVER AT N TROY, NY",
                    "siteCode": [{"value": "01358000", "network": "NWIS", "agencyCode": "USGS"}],
                    "geoLocation": {
                        "geogLocation": {"srs": "EPSG:4326", "latitude": 42.75, "longitude": -73.68}
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00060"}],
                    "variableName": "Streamflow, ft³/s",
                    "unit": {"unitCode": "ft3/s"},
                },
                "values": [{
                    "value": [
                        {"value": "8500", "qualifiers": [], "dateTime": "2026-09-01T00:00:00.000"},
                    ],
                }],
            },
        ],
    }
}


def _create_downloader(logger=None, sites="01646500"):
    if logger is None:
        logger = MockLogger()
    return USGSNWISDownloader(logger=logger, sites=sites)


def test_build_record():
    # Arrange
    downloader = _create_downloader()
    ts = SAMPLE_API_RESPONSE["value"]["timeSeries"][0]
    value_entry = ts["values"][0]["value"][0]
    site_info = ts["sourceInfo"]

    # Act
    record = downloader._build_record(ts, value_entry, site_info)

    # Assert
    assert record["site_id"] == "USGS-01646500"
    assert record["site_name"] == "POTOMAC RIVER NEAR WASH, DC"
    assert record["parameter_code"] == "00060"
    assert record["date"] == "2026-09-01"
    assert record["value"] == "2320"
    assert record["unit"] == "ft3/s"
    assert record["qualifiers"] == "P"
    assert record["latitude"] == 38.94977778
    assert record["longitude"] == -77.12763889


def test_build_url():
    # Arrange
    downloader = _create_downloader()

    # Act
    url = downloader._build_url(
        dt.datetime(2026, 9, 1),
        dt.datetime(2026, 9, 14),
    )

    # Assert
    assert "sites=01646500" in url
    assert "parameterCd=00060" in url
    assert "startDT=2026-09-01" in url
    assert "endDT=2026-09-14" in url
    assert "format=json" in url


def test_download_by_date_range():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(downloader, "_get_json", return_value=SAMPLE_API_RESPONSE):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert len(result) == 3
    assert result[0]["site_id"] == "USGS-01646500"
    assert result[0]["date"] == "2026-09-01"
    assert result[0]["value"] == "2320"
    assert result[1]["date"] == "2026-09-02"
    assert result[1]["value"] == "2220"
    assert result[2]["site_id"] == "USGS-01358000"
    assert result[2]["value"] == "8500"


def test_download_by_date_range_empty():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    empty_response = {"value": {"timeSeries": []}}
    with patch.object(downloader, "_get_json", return_value=empty_response):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []


def test_download_by_date_range_no_data():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(downloader, "_get_json", return_value=None):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []
