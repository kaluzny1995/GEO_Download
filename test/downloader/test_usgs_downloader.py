import datetime as dt
from unittest.mock import patch, MagicMock

import requests.exceptions

from downloader.usgs_earthquake import USGSEarthquakeDownloader

from test.downloader.conftest import MockLogger


def test_download_csv_success():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    csv_text = "time,latitude,longitude\n2026-09-01,40.0,-100.0\n2026-09-01,35.0,-90.0"
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [line.encode() for line in csv_text.splitlines()]
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert len(result) == 2
    assert result[0]["time"] == "2026-09-01"
    assert result[0]["latitude"] == "40.0"
    assert result[1]["longitude"] == "-90.0"
    assert any("Download successful" in msg for _, msg in logger.messages)


def test_download_csv_empty_response():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert result == []


def test_download_csv_http_error():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_csv_connection_error():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_by_date_range():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    csv_text = "time,latitude\n2026-09-01,40.0"
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [line.encode() for line in csv_text.splitlines()]
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert len(result) == 1
    called_url = mock_get.call_args[0][0]
    assert "starttime=2026-09-01" in called_url
    assert "endtime=2026-09-02" in called_url
    assert "format=csv" in called_url


def test_download_csv_only_csv_records():
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    csv_text = "time,mag,place\n2026-09-01,2.5,Near"
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [line.encode() for line in csv_text.splitlines()]
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert len(result) == 1
    assert set(result[0].keys()) == {"time", "mag", "place"}
