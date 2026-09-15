import pytest
import datetime as dt
import json
import os
from unittest.mock import patch, MagicMock, mock_open

from downloader.smithsonian_gvp import SmithsonianGVPDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))

    def warning(self, msg):
        self.messages.append(("WARNING", msg))


VOLCVIEW_DATA = [
    {"vnum": "311800", "vn": "Adagdak", "lat": 51.988, "lng": -176.592, "elevM": 610, "color": None, "obsAbbr": "AVO"},
    {"vnum": "332010", "vn": "Kilauea", "lat": 19.421, "lng": -155.287, "elevM": 1247, "color": None, "obsAbbr": "HVO"},
    {"vnum": "263280", "vn": "Agung", "lat": -8.343, "lng": 115.508, "elevM": 3142, "color": None, "obsAbbr": "PVMBG"},
]


def _create_downloader(logger=None):
    """Create a SmithsonianGVPDownloader with an empty country cache."""
    if logger is None:
        logger = MockLogger()
    with patch("os.path.exists", return_value=False):
        return SmithsonianGVPDownloader(logger=logger)


def test_load_country_cache():
    # Arrange
    logger = MockLogger()
    cache_data = {"51.9880,-176.5920": {"country_code": "US", "country_name": "United States"}}

    with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
        with patch("os.path.exists", return_value=True):
            downloader = SmithsonianGVPDownloader(logger=logger)

    # Assert
    assert len(downloader._country_cache) == 1
    assert downloader._country_cache["51.9880,-176.5920"]["country_code"] == "US"


def test_load_country_cache_no_file():
    # Arrange
    logger = MockLogger()

    with patch("os.path.exists", return_value=False):
        downloader = SmithsonianGVPDownloader(logger=logger)

    # Assert
    assert len(downloader._country_cache) == 0


def test_save_country_cache():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)
    downloader._country_cache = {"test": {"country_code": "US", "country_name": "USA"}}

    with patch("builtins.open", mock_open()) as mock_file:
        with patch("os.makedirs"):
            downloader._save_country_cache()

    # Assert
    mock_file.assert_called_once_with(downloader._cache_file, "w", encoding="utf-8")


def test_get_country_code_cached():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)
    downloader._country_cache = {"51.9880,-176.5920": {"country_code": "US", "country_name": "USA"}}

    # Act
    result = downloader._get_country_code(51.988, -176.592)

    # Assert
    assert result["country_code"] == "US"


def test_get_country_code_api_call():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {"countryCode": "ID", "countryName": "Indonesia"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader._get_country_code(-8.343, 115.508)

    # Assert
    assert result["country_code"] == "ID"
    assert result["country_name"] == "Indonesia"
    assert "-8.3430,115.5080" in downloader._country_cache


def test_get_country_code_api_error():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(downloader.session, "get", side_effect=Exception("Connection error")):
        # Act
        result = downloader._get_country_code(51.988, -176.592)

    # Assert
    assert result["country_code"] == ""
    assert result["country_name"] == ""
    assert any("Failed to geocode" in msg for _, msg in logger.messages)


def test_enrich_volcanoes_with_country():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)
    downloader._country_cache = {
        "51.9880,-176.5920": {"country_code": "US", "country_name": "USA"},
        "19.4210,-155.2870": {"country_code": "US", "country_name": "USA"},
    }

    # Act - only Agung (-8.3430,115.5080) is uncached, so _get_country_code is called once
    mock_response = MagicMock()
    mock_response.json.return_value = {"countryCode": "ID", "countryName": "Indonesia"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        enriched = downloader._enrich_volcanoes_with_country(VOLCVIEW_DATA)

    # Assert
    assert len(enriched) == 3
    assert enriched[0]["country_code"] == "US"
    assert enriched[1]["country_code"] == "US"
    assert enriched[2]["country_code"] == "ID"


def test_download_by_date_range():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    def mock_get_json(url):
        if "wwvolcanoes" in url:
            return VOLCVIEW_DATA
        return None

    mock_response = MagicMock()
    mock_response.json.return_value = {"countryCode": "US", "countryName": "USA"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(SmithsonianGVPDownloader, "_get_json", side_effect=mock_get_json):
        with patch.object(downloader.session, "get", return_value=mock_response):
            # Act
            result = downloader.download_by_date_range(
                "https://ignored.com",
                dt.datetime(2026, 9, 14),
                dt.datetime(2026, 9, 15),
            )

    # Assert
    assert len(result) == 3
    assert result[0]["vnum"] == "311800"
    assert result[0]["volcano_name"] == "Adagdak"
    assert result[0]["latitude"] == 51.988
    assert result[0]["longitude"] == -176.592
    assert result[0]["country_code"] == "US"


def test_download_by_date_range_no_data():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(SmithsonianGVPDownloader, "_get_json", return_value=None):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []


def test_download_by_date_range_empty_list():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(SmithsonianGVPDownloader, "_get_json", return_value=[]):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []


def test_download_by_date_range_not_a_list():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(SmithsonianGVPDownloader, "_get_json", return_value={"error": "not a list"}):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    # Assert
    assert result == []
