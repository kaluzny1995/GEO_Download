import pytest
import datetime as dt
from unittest.mock import patch, MagicMock

from downloader.usgs_volcano import USGSVolcanoDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))

    def warning(self, msg):
        self.messages.append(("WARNING", msg))


VOLCANO_CACHE = [
    {"volcano_cd": "ak111", "volcano_name": "Great Sitkin", "latitude": 52.0765,
     "longitude": -176.1109, "elevation_meters": 1740, "region": "Alaska - Aleutians",
     "vnum": "311120", "nvews_threat": "High Threat", "volcano_url": "https://example.com"},
    {"volcano_cd": "hi3", "volcano_name": "Kilauea", "latitude": 19.421,
     "longitude": -155.287, "elevation_meters": 1247, "region": "Hawaii",
     "vnum": "332010", "nvews_threat": "Very High Threat", "volcano_url": "https://example.com"},
]

NOTICES = [
    {
        "sent_utc": "2026-09-14 20:53:03",
        "notice_identifier": "DOI-USGS-AVO-2026-09-14T20:51:00+00:00",
        "volcanoes": "Great Sitkin",
        "notice_type_title": "Daily Update",
        "notice_type_cd": "DU",
        "notice_category": "Scheduled Update",
        "obs_fullname": "Alaska Volcano Observatory",
        "obs_abbr": "avo",
        "notice_url": "https://example.com/notice",
    },
    {
        "sent_utc": "2026-09-13 18:56:31",
        "notice_identifier": "DOI-USGS-AVO-2026-09-13T18:54:33+00:00",
        "volcanoes": "Great Sitkin, Kilauea",
        "notice_type_title": "Daily Update",
        "notice_type_cd": "DU",
        "notice_category": "Scheduled Update",
        "obs_fullname": "Alaska Volcano Observatory",
        "obs_abbr": "avo",
        "notice_url": "https://example.com/notice2",
    },
]

NOTICE_PARTS = {
    "notice_identifier": "DOI-USGS-AVO-2026-09-14T20:51:00+00:00",
    "sections": [
        {
            "volcano_cd": "ak111",
            "alert_level": "WATCH",
            "color_code": "ORANGE",
            "synopsis": "Lava continues to erupt.",
            "notice_number": "2026/A713",
        }
    ],
}


def test_load_volcano_cache():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    with patch.object(USGSVolcanoDownloader, "_get_json", return_value=VOLCANO_CACHE):
        # Act
        downloader._load_volcano_cache()

    # Assert
    assert len(downloader._volcano_cache) == 2
    assert downloader._name_to_code["Great Sitkin"] == "ak111"
    assert downloader._name_to_code["Kilauea"] == "hi3"


def test_load_volcano_cache_already_loaded():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)
    downloader._volcano_cache = {"ak111": VOLCANO_CACHE[0]}

    with patch.object(USGSVolcanoDownloader, "_get_json") as mock_get:
        # Act
        downloader._load_volcano_cache()

    # Assert
    mock_get.assert_not_called()


def test_get_volcano_codes_from_names():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)
    downloader._name_to_code = {"Great Sitkin": "ak111", "Kilauea": "hi3"}

    # Act
    codes = downloader._get_volcano_codes_from_names("Great Sitkin, Kilauea")

    # Assert
    assert codes == ["ak111", "hi3"]


def test_get_volcano_codes_from_names_unknown():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)
    downloader._name_to_code = {"Great Sitkin": "ak111"}

    # Act
    codes = downloader._get_volcano_codes_from_names("Great Sitkin, Unknown Volcano")

    # Assert
    assert codes == ["ak111"]
    assert any("No code found" in msg for _, msg in logger.messages)


def test_parse_sent_date():
    # Act & Assert
    assert USGSVolcanoDownloader._parse_sent_date("2026-09-14 20:53:03") == dt.date(2026, 9, 14)
    assert USGSVolcanoDownloader._parse_sent_date("invalid") is None
    assert USGSVolcanoDownloader._parse_sent_date("") is None


def test_build_record():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)
    downloader._volcano_cache = {"ak111": VOLCANO_CACHE[0]}

    notice = NOTICES[0]
    sent_date = dt.date(2026, 9, 14)

    # Act
    record = downloader._build_record(notice, "ak111", sent_date,
                                       alert_level="WATCH", color_code="ORANGE",
                                       notice_summary="Lava continues.", notice_number="2026/A713")

    # Assert
    assert record["country_code"] == "US"
    assert record["volcano_code"] == "ak111"
    assert record["volcano_name"] == "Great Sitkin"
    assert record["latitude"] == 52.0765
    assert record["longitude"] == -176.1109
    assert record["alert_level"] == "WATCH"
    assert record["color_code"] == "ORANGE"
    assert record["sent_date"] == "2026-09-14"


def test_download_by_date_range():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    def mock_get_json(url):
        if "getUSVolcanoes" in url:
            return VOLCANO_CACHE
        if "getRecentNotices" in url:
            return NOTICES
        if "getNoticeParts" in url:
            return NOTICE_PARTS
        return None

    with patch.object(USGSVolcanoDownloader, "_get_json", side_effect=mock_get_json):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 14),
            dt.datetime(2026, 9, 15),
        )

    # Assert
    assert len(result) == 1
    assert result[0]["volcano_code"] == "ak111"
    assert result[0]["alert_level"] == "WATCH"
    assert result[0]["color_code"] == "ORANGE"


def test_download_by_date_range_fallback_to_names():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    notices_no_sections = [NOTICES[1]]  # Has two volcano names

    def mock_get_json(url):
        if "getUSVolcanoes" in url:
            return VOLCANO_CACHE
        if "getRecentNotices" in url:
            return notices_no_sections
        if "getNoticeParts" in url:
            return {}  # No sections
        return None

    with patch.object(USGSVolcanoDownloader, "_get_json", side_effect=mock_get_json):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 13),
            dt.datetime(2026, 9, 14),
        )

    # Assert
    assert len(result) == 2
    codes = {r["volcano_code"] for r in result}
    assert codes == {"ak111", "hi3"}


def test_download_by_date_range_no_data():
    # Arrange
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    with patch.object(USGSVolcanoDownloader, "_get_json", return_value=None):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []
