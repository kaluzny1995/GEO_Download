import datetime as dt
from unittest.mock import MagicMock, patch

import requests.exceptions

from downloader.ibtracs import IBTrACSDownloader
from test.downloader.conftest import MockLogger

SAMPLE_CSV = (
    "SEASON,BASIN,SUBBASIN,ISO_TIME,NATURE,LAT,LON,WMO_WIND,WMO_PRES,DIST2LAND,LANDFALL\n"
    "SEASON,BASIN,SUBBASIN,ISO_TIME,NATURE,LAT,LON,WMO_WIND,WMO_PRES,DIST2LAND,LANDFALL\n"
    "2026,NA,GM,2026-09-01 06:00:00,TS,25.0,-80.0,35,1005,150,0\n"
    "2026,NA,GM,2026-09-01 12:00:00,TS,26.0,-81.0,40,1002,100,0\n"
    "2026,NA,GM,2026-09-02 06:00:00,HU,27.0,-82.0,65,990,50,0\n"
    "2026,WP,,2026-09-01 18:00:00,TS,15.0,135.0,45,998,200,0\n"
    "2026,WP,,2026-09-03 00:00:00,HU,16.0,136.0,80,970,500,0\n"
)

TEST_BASE_URL = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"


def _csv_to_bytes(text: str) -> list[bytes]:
    """Convert CSV text to list of byte lines for iter_lines() mock."""
    return [line.encode() for line in text.splitlines()]


def test_build_url():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    url = downloader._build_url(TEST_BASE_URL)
    assert "ibtracs.last3years.list.v04r01.csv" in url
    assert "ncei.noaa.gov" in url


def test_build_url_custom_dataset():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger, dataset="all")
    url = downloader._build_url(TEST_BASE_URL)
    assert "ibtracs.all.list.v04r01.csv" in url


def test_download_by_date_range_success():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert len(result) == 3
    for record in result:
        assert record["ISO_TIME"][:10] == "2026-09-01"
    called_url = mock_get.call_args[0][0]
    assert "ibtracs.last3years.list.v04r01.csv" in called_url


def test_download_by_date_range_filters_correctly():
    """Verify that only records in [start_date, end_date) are returned."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 2)
    end_date = dt.datetime(2026, 9, 3)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert len(result) == 1
    assert result[0]["ISO_TIME"] == "2026-09-02 06:00:00"


def test_download_by_date_range_no_match():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 10, 1)
    end_date = dt.datetime(2026, 10, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []


def test_download_by_date_range_skips_units_row():
    """The units row (row 2) must never appear in the output."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 3)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    for record in result:
        assert record.get("SEASON") != "SEASON"


def test_download_by_date_range_http_error():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_download_by_date_range_connection_error():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_download_by_date_range_empty_csv():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes("SEASON,BASIN\nSEASON,BASIN\n")
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []


def test_download_by_date_range_custom_dataset():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger, dataset="all")

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    called_url = mock_get.call_args[0][0]
    assert "ibtracs.all.list.v04r01.csv" in called_url
    assert len(result) == 3
