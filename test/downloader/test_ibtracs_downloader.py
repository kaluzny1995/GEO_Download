import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
import requests.exceptions

from downloader.ibtracs import IBTrACSDownloader
from test.downloader.conftest import MockLogger

SAMPLE_CSV = (
    "SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,NATURE,LAT,LON,WMO_WIND,WMO_PRES,DIST2LAND,LANDFALL\n"
    " ,Year, , , , , , , , , , , , \n"
    "2026001NA01,2026,1,NA,GM,GAMMA,2026-09-01 06:00:00,TS,25.0,-80.0,35,1005,150,0\n"
    "2026001NA01,2026,1,NA,GM,GAMMA,2026-09-01 12:00:00,TS,26.0,-81.0,40,1002,100,0\n"
    "2026001NA01,2026,1,NA,GM,GAMMA,2026-09-02 06:00:00,HU,27.0,-82.0,65,990,50,0\n"
    "2026002WP05,2026,2,WP,,,2026-09-01 18:00:00,TS,15.0,135.0,45,998,200,0\n"
    "2026002WP05,2026,2,WP,,,2026-09-03 00:00:00,HU,16.0,136.0,80,970,500,0\n"
)

TEST_BASE_URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"
)


def _csv_to_bytes(text: str) -> list[bytes]:
    """Convert CSV text to list of byte lines for iter_lines() mock."""
    return [line.encode() for line in text.splitlines()]


@pytest.mark.parametrize(
    ("downloader_kwargs", "expected_dataset_file"),
    [
        ({}, "ibtracs.last3years.list.v04r01.csv"),
        ({"dataset": "all"}, "ibtracs.all.list.v04r01.csv"),
    ],
)
def test_build_url(downloader_kwargs, expected_dataset_file):
    downloader = IBTrACSDownloader(logger=MockLogger(), **downloader_kwargs)
    url = downloader._build_url(TEST_BASE_URL)
    assert expected_dataset_file in url
    assert "ncei.noaa.gov" in url


@pytest.mark.parametrize(
    ("start_date", "end_date", "expected_times"),
    [
        (
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
            ["2026-09-01 06:00:00", "2026-09-01 12:00:00", "2026-09-01 18:00:00"],
        ),
        (dt.datetime(2026, 9, 2), dt.datetime(2026, 9, 3), ["2026-09-02 06:00:00"]),
        (dt.datetime(2026, 10, 1), dt.datetime(2026, 10, 2), []),
    ],
)
def test_download_by_date_range(start_date, end_date, expected_times):
    """Only records in [start_date, end_date) are returned — ISO_TIME resolved by header name."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert [record["ISO_TIME"] for record in result] == expected_times
    called_url = mock_get.call_args[0][0]
    assert "ibtracs.last3years.list.v04r01.csv" in called_url


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

    assert len(result) == 4
    for record in result:
        assert record.get("SEASON") != "Year"
        assert record.get("ISO_TIME") != ""


def test_download_by_date_range_resolves_iso_time_by_name():
    """ISO_TIME must be located by header name, not by a fixed column index."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    # ISO_TIME deliberately not in the position used by the live IBTrACS file.
    csv_text = (
        "SID,ISO_TIME,BASIN,SEASON,NAME\n"
        " , , ,Year, \n"
        "2026001NA01,2026-09-01 06:00:00,NA,2026,GAMMA\n"
        "2026001NA01,2026-09-05 06:00:00,NA,2026,GAMMA\n"
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(csv_text)
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert len(result) == 1
    assert result[0]["ISO_TIME"] == "2026-09-01 06:00:00"
    assert result[0]["SID"] == "2026001NA01"


def test_download_by_date_range_missing_iso_time_column():
    """A header without ISO_TIME must fail loudly instead of returning nothing silently."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes("SID,SEASON,BASIN\n ,Year,NA\n")
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("has no ISO_TIME column" in msg for _, msg in logger.messages)


@pytest.mark.parametrize("error_mode", ["http-error", "connection-error"])
def test_download_by_date_range_fetch_errors(error_mode):
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    if error_mode == "http-error":
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        get_patcher = patch.object(downloader.session, "get", return_value=mock_response)
    else:
        get_patcher = patch.object(
            downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")
        )

    with get_patcher:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_download_by_date_range_empty_csv():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes("SID,SEASON,ISO_TIME\n ,Year, \n")
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


def test_download_stamps_geocode_pair_with_near_land_filter(tmp_path):
    """Near-land rows are geocoded; far rows get the cached answer or an empty stamp."""
    from reverse_geocode import coord_key, save_cache

    lookup = tmp_path / "reverse_geocode.csv"
    save_cache({coord_key(15.0, 135.0): ("PH", "PSA")}, str(lookup))
    downloader = IBTrACSDownloader(logger=MockLogger(), reverse_geocode_file=str(lookup))

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = _csv_to_bytes(SAMPLE_CSV)
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 4)
        )

    by_key = {(record["LAT"], record["LON"]): record for record in result}
    assert by_key[("26.0", "-81.0")]["geocode_state"] == "MT"  # DIST2LAND 100 → fetched
    assert by_key[("27.0", "-82.0")]["geocode_country"] == "US"  # DIST2LAND 50 → fetched
    assert by_key[("15.0", "135.0")]["geocode_state"] == "PSA"  # far, but cached
    assert by_key[("25.0", "-80.0")]["geocode_country"] == ""  # DIST2LAND 150, not cached
