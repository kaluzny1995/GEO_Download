import datetime as dt
from unittest.mock import MagicMock, patch

import requests.exceptions

from downloader.nifc import NIFCDownloader, _state_code
from test.downloader.conftest import MockLogger

TEST_BASE_URL = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"


def test_build_record():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {
            "poly_IncidentName": "Iron Fire",
            "poly_IRWINID": "{B22F7798-E3C3-4E1B-A091-CC85EBE4DA75}",
            "poly_FeatureCategory": "Wildfire Daily Fire Perimeter",
            "poly_GISAcres": 1500.5,
            "poly_DateCurrent": 1789573862000,
            "attr_IncidentTypeCategory": "WF",
            "attr_FireDiscoveryDateTime": 1781935269010,
            "attr_PercentContained": 45.0,
            "attr_POOJurisdictionalAgency": "BLM",
            "attr_POOJurisdictionalUnit": "NVNV0100",
            "attr_POOState": "US-UT",
            "attr_InitialLatitude": 39.9,
            "attr_InitialLongitude": -111.9,
            "attr_CreatedOnDateTime_dt": 1781935269010,
            "attr_ModifiedOnDateTime_dt": 1788887907813,
        },
        "centroid": {"x": -112.14269529210874, "y": 40.017760846821886},
    }

    record = downloader._build_record(feature)

    assert record["incident_name"] == "Iron Fire"
    assert record["irwin_id"] == "{B22F7798-E3C3-4E1B-A091-CC85EBE4DA75}"
    assert record["fire_number"] == 1781935269010
    assert record["acres"] == 1500.5
    assert record["percent_contained"] == 45.0
    assert record["fire_type"] == "WF"
    assert record["fire_type_label"] == "Wildfire Daily Fire Perimeter"
    assert record["jurisdiction"] == "BLM"
    assert record["jurisdiction_label"] == "NVNV0100"
    assert record["state"] == "UT"
    assert record["po_method"] == "US-UT"
    assert record["latitude"] == 40.017760846821886
    assert record["longitude"] == -112.14269529210874
    assert record["poly_date"] == 1789573862000
    assert record["created_on"] == 1781935269010
    assert record["modified_on"] == 1788887907813


def test_build_record_maps_null_attributes_to_empty_string():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {
            "poly_IncidentName": "Crosswhite",
            "poly_GISAcres": 355064.56,
            "attr_PercentContained": None,
            "attr_POOJurisdictionalAgency": None,
            "attr_POOJurisdictionalUnit": None,
        },
        "centroid": {"x": -120.49, "y": 44.61},
    }

    record = downloader._build_record(feature)

    assert record["acres"] == 355064.56
    assert record["percent_contained"] == ""
    assert record["jurisdiction"] == ""
    assert record["jurisdiction_label"] == ""
    assert record["state"] == ""
    assert record["po_method"] == ""


def test_build_record_without_coordinates():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {"poly_IncidentName": "Test"},
    }

    record = downloader._build_record(feature)

    assert record["incident_name"] == "Test"
    assert record["latitude"] == ""
    assert record["longitude"] == ""


def test_build_record_falls_back_to_point_of_origin():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    feature = {
        "attributes": {
            "attr_InitialLatitude": 40.5,
            "attr_InitialLongitude": -99.5,
        },
    }

    record = downloader._build_record(feature)

    assert record["latitude"] == 40.5
    assert record["longitude"] == -99.5


def test_state_code():
    assert _state_code("US-CO") == "CO"
    assert _state_code("UT") == "UT"
    assert _state_code("") == ""


def test_out_fields_contain_no_whitespace():
    for field in NIFCDownloader._OUT_FIELDS:
        assert field.strip() == field, f"{field!r} has surrounding whitespace"
        assert " " not in field, f"{field!r} is not a valid ArcGIS field name"


def test_download_by_date_range_success():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "features": [
            {
                "attributes": {"poly_IncidentName": "Fire1"},
                "centroid": {"x": -100.0, "y": 40.0},
            },
            {
                "attributes": {"poly_IncidentName": "Fire2"},
                "centroid": {"x": -101.0, "y": 41.0},
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
    assert result[1]["latitude"] == 41.0


def test_download_by_date_range_api_error_payload():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "error": {
            "code": 400,
            "message": "Unable to complete operation.",
            "details": ["'outFields' parameter is invalid"],
        }
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))

    assert result == []
    assert any("rejected the query" in msg and "outFields" in msg for _, msg in logger.messages)


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

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = downloader.download_by_date_range(
            TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


def test_download_by_date_range_builds_correct_query():
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
    assert "returnGeometry=false" in called_url
    assert "returnCentroid=true" in called_url
    assert "outSR=4326" in called_url
    assert "poly_GISAcres" in called_url
    assert "poly_GIS%20Acres" not in called_url
