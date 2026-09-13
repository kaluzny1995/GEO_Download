import pytest
from unittest.mock import patch, MagicMock

from usgs.downloader import USGSDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))


def test_download_csv_success():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = "time,latitude,longitude\n2026-09-01,40.0,-100.0\n2026-09-01,35.0,-90.0"
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader.download_csv("https://example.com/api?format=csv")

    # Assert
    assert len(result) == 2
    assert result[0]["time"] == "2026-09-01"
    assert result[0]["latitude"] == "40.0"
    assert result[1]["longitude"] == "-90.0"
    assert any("Download successful" in msg for _, msg in logger.messages)


def test_download_csv_empty_response():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = ""
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader.download_csv("https://example.com/api?format=csv")

    # Assert
    assert result == []


def test_download_csv_http_error():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("500 Server Error")

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader.download_csv("https://example.com/api?format=csv")

    # Assert
    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_csv_connection_error():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=Exception("Connection refused")):
        # Act
        result = downloader.download_csv("https://example.com/api?format=csv")

    # Assert
    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_by_date_range():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = "time,latitude\n2026-09-01,40.0"
    mock_response.raise_for_status = MagicMock()

    import datetime as dt
    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        # Act
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    # Assert
    assert len(result) == 1
    called_url = mock_get.call_args[0][0]
    assert "starttime=2026-09-01" in called_url
    assert "endtime=2026-09-02" in called_url
    assert "format=csv" in called_url


def test_download_csv_only_csv_records():
    # Arrange
    logger = MockLogger()
    downloader = USGSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = "time,mag,place\n2026-09-01,2.5,Near"
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        # Act
        result = downloader.download_csv("https://example.com/api?format=csv")

    # Assert
    assert len(result) == 1
    assert set(result[0].keys()) == {"time", "mag", "place"}
