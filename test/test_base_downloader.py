import pytest
from unittest.mock import patch, MagicMock
import datetime as dt

from downloader.base import BaseDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
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


def test_cannot_instantiate_base_directly():
    # Act & Assert
    with pytest.raises(TypeError):
        BaseDownloader(logger=MockLogger())


def test_create_session_has_retry():
    # Act
    session = BaseDownloader._create_session()

    # Assert
    assert "https://" in session.adapters
    assert "http://" in session.adapters


def test_get_json_success():
    # Arrange
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {"key": "value"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader._get_json("https://example.com/api")

    # Assert
    assert result == {"key": "value"}


def test_get_json_error():
    # Arrange
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=Exception("Connection error")):
        # Act
        result = downloader._get_json("https://example.com/api")

    # Assert
    assert result is None
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_logger_name():
    # Arrange & Act
    logger = MockLogger()
    eq_downloader = USGSEarthquakeDownloader(logger=logger)
    vol_downloader = SmithsonianGVPDownloader(logger=logger)

    # Assert
    assert eq_downloader.logger is logger
    assert vol_downloader.logger is logger
