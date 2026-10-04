import datetime as dt
import json
import os
import tempfile
from unittest.mock import patch

from downloader.base import BaseDownloader
from downloader.openmeteo_flood import OpenMeteoFloodDownloader
from test.downloader.conftest import MockLogger

SAMPLE_RIVERS = [
    {"name": "Danube", "country": "Romania", "latitude": 44.42, "longitude": 28.63},
    {"name": "Rhine", "country": "Netherlands", "latitude": 51.85, "longitude": 4.25},
    {"name": "Nile", "country": "Egypt", "latitude": 30.05, "longitude": 31.23},
]

SAMPLE_API_RESPONSE = {
    "latitude": 44.42,
    "longitude": 28.63,
    "daily": {
        "time": ["2026-09-01", "2026-09-02", "2026-09-03"],
        "river_discharge": [5500.0, 5620.0, 5780.0],
    },
}

SAMPLE_API_RESPONSE_WITH_NULL = {
    "latitude": 30.05,
    "longitude": 31.23,
    "daily": {
        "time": ["2026-09-01", "2026-09-02"],
        "river_discharge": [None, 2100.0],
    },
}

SAMPLE_API_RESPONSE_EMPTY = {
    "latitude": 0.0,
    "longitude": 0.0,
    "daily": {
        "time": [],
        "river_discharge": [],
    },
}


def _create_downloader(rivers=None, logger=None):
    if logger is None:
        logger = MockLogger()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(rivers or SAMPLE_RIVERS, f)
        temp_path = f.name
    try:
        return OpenMeteoFloodDownloader(logger=logger, rivers_file=temp_path)
    finally:
        os.unlink(temp_path)


def test_load_rivers():
    # Arrange & Act
    downloader = _create_downloader()

    # Assert
    assert len(downloader._rivers) == 3
    assert downloader._rivers[0]["name"] == "Danube"


def test_build_records():
    # Arrange
    downloader = _create_downloader()

    # Act
    records = downloader._build_records(
        SAMPLE_RIVERS[0],
        SAMPLE_API_RESPONSE,
    )

    # Assert
    assert len(records) == 3
    assert records[0]["river_name"] == "Danube"
    assert records[0]["country"] == "Romania"
    assert records[0]["latitude"] == 44.42
    assert records[0]["longitude"] == 28.63
    assert records[0]["date"] == "2026-09-01"
    assert records[0]["discharge_m3s"] == 5500.0
    assert records[2]["date"] == "2026-09-03"
    assert records[2]["discharge_m3s"] == 5780.0


def test_build_records_skips_null():
    # Arrange
    downloader = _create_downloader()

    # Act
    records = downloader._build_records(
        SAMPLE_RIVERS[2],
        SAMPLE_API_RESPONSE_WITH_NULL,
    )

    # Assert
    assert len(records) == 1
    assert records[0]["date"] == "2026-09-02"
    assert records[0]["discharge_m3s"] == 2100.0


def test_build_records_empty():
    # Arrange
    downloader = _create_downloader()

    # Act
    records = downloader._build_records(
        SAMPLE_RIVERS[0],
        SAMPLE_API_RESPONSE_EMPTY,
    )

    # Assert
    assert records == []


def test_download_by_date_range():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger=logger)

    responses = [SAMPLE_API_RESPONSE, SAMPLE_API_RESPONSE, SAMPLE_API_RESPONSE_WITH_NULL]
    call_count = 0

    def mock_get_json(_url):
        nonlocal call_count
        resp = responses[call_count] if call_count < len(responses) else None
        call_count += 1
        return resp

    with patch.object(BaseDownloader, "_get_json", side_effect=mock_get_json):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 1),
        )

    # Assert
    assert len(result) == 7  # 3 + 3 + 1 (null skipped)
    assert result[0]["river_name"] == "Danube"
    assert result[3]["river_name"] == "Rhine"
    assert result[6]["river_name"] == "Nile"
    assert call_count == 3


def test_download_by_date_range_all_null():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger=logger)

    null_response = {
        "latitude": 0.0,
        "longitude": 0.0,
        "daily": {"time": ["2026-09-01"], "river_discharge": [None]},
    }

    with patch.object(BaseDownloader, "_get_json", return_value=null_response):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 1),
        )

    # Assert
    assert result == []


def test_download_by_date_range_api_error():
    # Arrange
    logger = MockLogger()
    downloader = _create_downloader(logger=logger)

    with patch.object(BaseDownloader, "_get_json", return_value=None):
        # Act
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 1),
        )

    # Assert
    assert result == []


def test_download_stamps_geocode_country_and_state(tmp_path):
    """Every river point is reverse-geocoded into the stamped pair."""
    rivers_file = tmp_path / "rivers.json"
    rivers_file.write_text(json.dumps(SAMPLE_RIVERS))
    lookup = str(tmp_path / "reverse_geocode.csv")
    downloader = OpenMeteoFloodDownloader(
        logger=MockLogger(), rivers_file=str(rivers_file), reverse_geocode_file=lookup
    )

    with patch.object(downloader, "_query_river", return_value=SAMPLE_API_RESPONSE):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 3),
        )

    assert len(result) == 9
    assert all(record["geocode_country"] == "US" for record in result)
    assert all(record["geocode_state"] == "MT" for record in result)
