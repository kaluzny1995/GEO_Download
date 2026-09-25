import datetime as dt
from unittest.mock import MagicMock, patch

import requests.exceptions

from downloader.usgs_volcano import USGSVolcanoDownloader
from test.downloader.conftest import MockLogger

TEST_BASE_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano"


def test_build_record():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    volcano = {
        "volcano_name": "Great Sitkin",
        "vnum": "1203-01-",
        "obs_abbr": "AVO",
        "obs_fullname": "Alaska Volcano Observatory",
        "alert_level": "ADVISORY",
        "color_code": "YELLOW",
        "notice_type_cd": "VONA",
        "notice_identifier": "VOA030",
        "sent_utc": "2026-09-09T14:30:00Z",
        "notice_url": "https://volcanoes.usgs.gov/vns2/volcano.html?vid=1203010",
    }

    record = downloader._build_record(volcano)

    assert record["volcano_name"] == "Great Sitkin"
    assert record["vnum"] == "1203-01-"
    assert record["observatory"] == "AVO"
    assert record["observatory_name"] == "Alaska Volcano Observatory"
    assert record["alert_level"] == "ADVISORY"
    assert record["color_code"] == "YELLOW"
    assert record["notice_type"] == "VONA"
    assert record["notice_identifier"] == "VOA030"
    assert record["notice_date"] == "2026-09-09T14:30:00Z"
    assert record["notice_url"] == "https://volcanoes.usgs.gov/vns2/volcano.html?vid=1203010"


def test_build_record_empty():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    record = downloader._build_record({})

    assert record["volcano_name"] == ""
    assert record["alert_level"] == ""
    assert record["notice_date"] == ""


def test_download_by_date_range_success():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "volcano_name": "Great Sitkin",
            "vnum": "1203-01-",
            "obs_abbr": "AVO",
            "alert_level": "ADVISORY",
            "color_code": "YELLOW",
            "notice_type_cd": "VONA",
            "notice_identifier": "VOA030",
            "sent_utc": "2026-09-09T14:30:00Z",
            "notice_url": "https://example.com/volcano",
        },
        {
            "volcano_name": "Shishaldin",
            "vnum": "1203-02-",
            "obs_abbr": "AVO",
            "alert_level": "WATCH",
            "color_code": "ORANGE",
            "notice_type_cd": "VONA",
            "notice_identifier": "VOA031",
            "sent_utc": "2026-09-10T10:00:00Z",
            "notice_url": "https://example.com/volcano2",
        },
    ]
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 17)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 2
    assert result[0]["volcano_name"] == "Great Sitkin"
    assert result[1]["volcano_name"] == "Shishaldin"


def test_download_by_date_range_filters_by_date():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "volcano_name": "Volcano A",
            "sent_utc": "2026-09-01T10:00:00Z",
        },
        {
            "volcano_name": "Volcano B",
            "sent_utc": "2026-09-10T10:00:00Z",
        },
    ]
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 5)
    end_date = dt.datetime(2026, 9, 12)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 1
    assert result[0]["volcano_name"] == "Volcano B"


def test_download_by_date_range_empty():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 17)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 0
    assert any("No data received" in msg for _, msg in logger.messages)


def test_download_by_date_range_none_response():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = None
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 17)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 0


def test_download_by_date_range_connection_error():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)
