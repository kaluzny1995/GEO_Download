import pytest
import datetime as dt
from unittest.mock import patch, MagicMock

from downloader.nifc import NIFCDownloader


class MockLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("INFO", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))

    def warning(self, msg):
        self.messages.append(("WARNING", msg))


TEST_BASE_URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"


def test_build_record():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {
            "poly_IncidentName": "Iron Fire",
            "poly_IRWINID": "{B22F7798-E3C3-4E1B-A091-CC85EBE4DA75}",
            "poly_FireDiscoveryDateTime": 1781935269010,
            "poly_GIS Acres": 1500.5,
            "poly_PercentContained": 45.0,
            "poly_FireType": "WF",
            "poly_FireType_LABEL": "Wildfire",
            "poly_Jurisdiction": "BLM",
            "poly_Jurisdiction_LABEL": "Bureau of Land Management",
            "poly_State": "UT",
            "poly_POOState": "US-UT",
            "poly_DateCurrent": 1789573862000,
            "attr_CreatedOnDateTime_dt": 1781935269010,
            "attr_ModifiedOnDateTime_dt": 1788887907813,
        },
        "geometry": {
            "rings": [
                [
                    [-112.14269529210874, 40.017760846821886],
                    [-112.14269529210874, 40.017760846821886],
                ]
            ]
        },
    }

    record = downloader._build_record(feature)

    assert record["incident_name"] == "Iron Fire"
    assert record["irwin_id"] == "{B22F7798-E3C3-4E1B-A091-CC85EBE4DA75}"
    assert record["fire_number"] == 1781935269010
    assert record["acres"] == 1500.5
    assert record["percent_contained"] == 45.0
    assert record["fire_type"] == "WF"
    assert record["fire_type_label"] == "Wildfire"
    assert record["jurisdiction"] == "BLM"
    assert record["jurisdiction_label"] == "Bureau of Land Management"
    assert record["state"] == "UT"
    assert record["po_method"] == "US-UT"
    assert record["poly_date"] == 1789573862000
    assert record["created_on"] == 1781935269010
    assert record["modified_on"] == 1788887907813


def test_build_record_empty_geometry():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {"poly_IncidentName": "Test"},
        "geometry": {},
    }

    record = downloader._build_record(feature)

    assert record["incident_name"] == "Test"
    assert record["latitude"] == ""
    assert record["longitude"] == ""


def test_build_record_centroid_calculation():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {},
        "geometry": {
            "rings": [
                [
                    [-100.0, 40.0],
                    [-100.0, 41.0],
                    [-99.0, 41.0],
                    [-99.0, 40.0],
                ]
            ]
        },
    }

    record = downloader._build_record(feature)

    assert record["latitude"] == pytest.approx(40.5, rel=1e-2)
    assert record["longitude"] == pytest.approx(-99.5, rel=1e-2)


def test_download_by_date_range_success():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "features": [
            {
                "attributes": {"poly_IncidentName": "Fire1"},
                "geometry": {"rings": [[[-100.0, 40.0]]]},
            },
            {
                "attributes": {"poly_IncidentName": "Fire2"},
                "geometry": {"rings": [[[-101.0, 41.0]]]},
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 2
    assert result[0]["incident_name"] == "Fire1"
    assert result[1]["incident_name"] == "Fire2"


def test_download_by_date_range_empty_features():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {"features": []}
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 0


def test_download_by_date_range_none_response():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = None
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    assert len(result) == 0
    assert any("No data received" in msg for _, msg in logger.messages)


def test_download_by_date_range_connection_error():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    with patch.object(downloader.session, "get", side_effect=Exception("Connection refused")):
        result = downloader.download_by_date_range(
            TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_download_by_date_range_builds_correct_where_clause():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {"features": []}
    mock_response.raise_for_status = MagicMock()

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 17)

    with patch.object(downloader.session, "get", return_value=mock_response) as mock_get:
        downloader.download_by_date_range(TEST_BASE_URL, start_date, end_date)

    called_url = mock_get.call_args[0][0]
    assert "poly_DateCurrent >= TIMESTAMP '2026-09-01 00:00:00'" in called_url
    assert "poly_DateCurrent <= TIMESTAMP '2026-09-17 00:00:00'" in called_url
    assert "returnGeometry=true" in called_url
    assert "outSR=4326" in called_url
