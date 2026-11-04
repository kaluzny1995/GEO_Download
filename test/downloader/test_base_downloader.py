from unittest.mock import MagicMock, patch

import pytest
import requests.exceptions

from downloader.base import BaseDownloader
from downloader.eonet import EONETDownloader
from downloader.gdacs import GDACSDownloader
from downloader.openmeteo_flood import OpenMeteoFloodDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
from downloader.usgs_nwis import USGSNWISDownloader
from test.downloader.conftest import MockLogger


def test_cannot_instantiate_base_directly():
    with pytest.raises(TypeError):
        # noinspection PyAbstractClass
        BaseDownloader(logger=MockLogger())


def test_create_session_has_retry():
    session = BaseDownloader._create_session()

    assert "https://" in session.adapters
    assert "http://" in session.adapters


def test_create_session_identifies_the_client():
    """The session sends a descriptive User-Agent instead of the default python-requests one."""
    session = BaseDownloader._create_session()

    assert session.headers["User-Agent"] == "GEO_Download/1.0"


def test_get_json_success():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {"key": "value"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader._get_json("https://example.com/api")

    assert result == {"key": "value"}


def test_get_json_error():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection error")):
        result = downloader._get_json("https://example.com/api")

    assert result is None
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_logger_name():
    logger = MockLogger()
    eq_downloader = USGSEarthquakeDownloader(logger=logger)
    gdacs_downloader = GDACSDownloader(logger=logger)
    eonet_downloader = EONETDownloader(logger=logger)
    flood_downloader = OpenMeteoFloodDownloader(logger=logger)
    nwis_downloader = USGSNWISDownloader(logger=logger)

    assert eq_downloader.logger is logger
    assert gdacs_downloader.logger is logger
    assert eonet_downloader.logger is logger
    assert flood_downloader.logger is logger
    assert nwis_downloader.logger is logger
