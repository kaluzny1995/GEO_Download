import pytest
import datetime as dt
from unittest.mock import patch, MagicMock

from downloader.ibtracs import IBTrACSDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))

    def warning(self, msg):
        self.messages.append(("WARNING", msg))


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


def test_parse_csv_success():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv(SAMPLE_CSV)
    assert len(records) == 5
    assert records[0]["SEASON"] == "2026"
    assert records[0]["BASIN"] == "NA"
    assert records[0]["ISO_TIME"] == "2026-09-01 06:00:00"
    assert records[0]["LAT"] == "25.0"
    assert records[0]["LON"] == "-80.0"
    assert records[0]["WMO_WIND"] == "35"


def test_parse_csv_units_row_skipped():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv(SAMPLE_CSV)
    for record in records:
        assert record.get("SEASON") != "SEASON"


def test_parse_csv_empty():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv("")
    assert records == []


def test_parse_csv_too_few_lines():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv("col1,col2\n")
    assert records == []
    assert any("fewer than 3 lines" in msg for _, msg in logger.messages)


def test_filter_by_date():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv(SAMPLE_CSV)
    start = dt.datetime(2026, 9, 1)
    end = dt.datetime(2026, 9, 2)
    filtered = downloader._filter_by_date(records, start, end)
    assert len(filtered) == 3
    for record in filtered:
        date_str = record["ISO_TIME"][:10]
        assert "2026-09-01" <= date_str < "2026-09-02"


def test_filter_by_date_single_day():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv(SAMPLE_CSV)
    start = dt.datetime(2026, 9, 2)
    end = dt.datetime(2026, 9, 3)
    filtered = downloader._filter_by_date(records, start, end)
    assert len(filtered) == 1
    assert filtered[0]["ISO_TIME"] == "2026-09-02 06:00:00"


def test_filter_by_date_no_match():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = downloader._parse_csv(SAMPLE_CSV)
    start = dt.datetime(2026, 10, 1)
    end = dt.datetime(2026, 10, 2)
    filtered = downloader._filter_by_date(records, start, end)
    assert len(filtered) == 0


def test_filter_by_date_empty_iso_time():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)
    records = [{"ISO_TIME": ""}, {"ISO_TIME": "2026-09-01 12:00:00"}]
    start = dt.datetime(2026, 9, 1)
    end = dt.datetime(2026, 9, 2)
    filtered = downloader._filter_by_date(records, start, end)
    assert len(filtered) == 1


def test_download_by_date_range_success():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = SAMPLE_CSV
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert len(result) == 3
    called_url = mock_get.call_args[0][0]
    assert "ibtracs.last3years.list.v04r01.csv" in called_url


def test_download_by_date_range_http_error():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("500 Server Error")

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_by_date_range_connection_error():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", side_effect=Exception("Connection refused")):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("Download failed" in msg for _, msg in logger.messages)


def test_download_by_date_range_empty_csv():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.text = "SEASON,BASIN\nSEASON,BASIN\n"
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
    mock_response.text = SAMPLE_CSV
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    called_url = mock_get.call_args[0][0]
    assert "ibtracs.all.list.v04r01.csv" in called_url
