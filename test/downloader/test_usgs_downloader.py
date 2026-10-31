import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
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


@pytest.mark.parametrize("error_mode", ["empty", "http-error", "connection-error"])
def test_download_csv_failure_modes(error_mode):
    logger = MockLogger()
    downloader = USGSEarthquakeDownloader(logger=logger)

    if error_mode == "empty":
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = []
        mock_response.raise_for_status = MagicMock()
        get_patcher = patch.object(downloader.session, "get", return_value=mock_response)
    elif error_mode == "http-error":
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        get_patcher = patch.object(downloader.session, "get", return_value=mock_response)
    else:
        get_patcher = patch.object(
            downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")
        )

    with get_patcher:
        result = downloader._download_csv("https://example.com/api?format=csv")

    assert result == []
    if error_mode != "empty":
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


def test_place_suffix_extraction():
    from downloader.usgs_earthquake import _place_suffix

    assert _place_suffix("9 km WSW of Idyllwild, CA") == "CA"
    assert _place_suffix("Chile") == ""
    assert _place_suffix("A, B, Anchorage, AK") == "AK"
    assert _place_suffix(None) == ""


def test_country_known_place_suffixes():
    from downloader.usgs_earthquake import _country_known

    assert _country_known("5 km SW of Boulder, CO")
    assert _country_known("12 km NE of Valparaiso, Chile")
    assert _country_known("Somewhere, Puerto Rico")
    assert not _country_known("Chile")  # no comma → no suffix → geocoded, like the ETL
    assert not _country_known("Bouvet Island region")
    assert not _country_known(None)


def test_download_stamps_only_suffix_unknown_places(tmp_path):
    """A US-suffixed place keeps an empty stamp; an unknown suffix gets the geocode."""
    lookup = str(tmp_path / "reverse_geocode.csv")
    downloader = USGSEarthquakeDownloader(logger=MockLogger(), reverse_geocode_file=lookup)

    csv_text = (
        "time,latitude,longitude,place\n"
        '2026-09-01T00:00:00.000Z,40.0,-105.0,"5 km SW of Boulder, CO"\n'
        "2026-09-01T01:00:00.000Z,60.0,-170.0,Bouvet Island region\n"
    )
    mock_response = MagicMock()
    mock_response.iter_lines.return_value = [line.encode() for line in csv_text.splitlines()]
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )

    assert result[0]["geocode_country"] == ""
    assert result[0]["geocode_state"] == ""
    assert result[1]["geocode_country"] == "US"
    assert result[1]["geocode_state"] == "MT"
