import datetime as dt
import os
from unittest.mock import MagicMock, patch

import pytest
import requests.exceptions

from downloader.nifc import NIFCDownloader, _name_by_code, _state_code
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
    assert record["unit_name"] == ""
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


def test_build_record_keeps_unit_name_next_to_the_code():
    logger = MockLogger()
    downloader = NIFCDownloader(logger=logger)

    record = downloader._build_record({"attributes": {"attr_POOJurisdictionalUnit": "WAOWF"}})

    keys = list(record.keys())
    assert keys[keys.index("jurisdiction_label") + 1] == "unit_name"
    assert keys[keys.index("unit_name") + 1] == "state"


def test_default_unit_names_file_points_next_to_rivers_json():
    downloader = NIFCDownloader(logger=MockLogger())

    assert downloader.unit_names_file == NIFCDownloader.DEFAULT_UNIT_NAMES_FILE
    assert downloader.unit_names_file.endswith(os.path.join("data", "nifc_unit_names.csv"))


PAIRS = {
    ("WAOWF", "Okanogan-Wenatchee National Forest"),
    ("CAYNP", "Yosemite National Park"),
    ("WANES", "Colville National Forest"),
    ("WANES", "Alpine Lakes Wilderness"),
}


def _pairs_payload(pairs=PAIRS):
    return {
        "features": [
            {"attributes": {"JurisdictionalUnitID_sansUS": code, "JurisdictionalUnitName": name}}
            for code, name in pairs
        ]
    }


def _downloader(tmp_path) -> NIFCDownloader:
    return NIFCDownloader(logger=MockLogger(), unit_names_file=str(tmp_path / "nifc_unit_names.csv"))


def _write_lookup(tmp_path, codes=("WAOWF", "CAYNP")) -> str:
    output = tmp_path / "nifc_unit_names.csv"
    rows = "".join(f"{code},Name of {code}\n" for code in codes)
    output.write_text(f"unit_code,unit_name\n{rows}")
    return str(output)


class TestFetchPairs:
    @patch("downloader.base.BaseDownloader._get_json")
    def test_returns_distinct_pairs(self, mock_get_json, tmp_path):
        mock_get_json.return_value = _pairs_payload()

        pairs = _downloader(tmp_path)._fetch_pairs("https://example.test/query")

        assert pairs == PAIRS
        url = mock_get_json.call_args.args[0]
        assert "returnDistinctValues=true" in url
        assert "JurisdictionalUnitID_sansUS+IS+NOT+NULL" in url

    @patch("downloader.base.BaseDownloader._get_json")
    def test_skips_blank_codes_and_names(self, mock_get_json, tmp_path):
        mock_get_json.return_value = {
            "features": [
                {"attributes": {"JurisdictionalUnitID_sansUS": "WAOWF", "JurisdictionalUnitName": "Ok forests"}},
                {"attributes": {"JurisdictionalUnitID_sansUS": "", "JurisdictionalUnitName": "Private parcel"}},
                {"attributes": {"JurisdictionalUnitID_sansUS": None, "JurisdictionalUnitName": "Private parcel 2"}},
                {"attributes": {"JurisdictionalUnitID_sansUS": "CAYNP", "JurisdictionalUnitName": ""}},
                {"attributes": {}},
            ]
        }

        pairs = _downloader(tmp_path)._fetch_pairs("https://example.test/query")

        assert pairs == {("WAOWF", "Ok forests")}

    @patch("downloader.base.BaseDownloader._get_json")
    def test_error_payload_raises(self, mock_get_json, tmp_path):
        mock_get_json.return_value = {"error": {"code": 400, "message": "Invalid query."}}

        with pytest.raises(RuntimeError, match="rejected the query: Invalid query"):
            _downloader(tmp_path)._fetch_pairs("https://example.test/query")

    @patch("downloader.base.BaseDownloader._get_json")
    def test_empty_features_raise(self, mock_get_json, tmp_path):
        mock_get_json.return_value = {"features": []}

        with pytest.raises(RuntimeError, match="no code/name pairs"):
            _downloader(tmp_path)._fetch_pairs("https://example.test/query")

    @patch("downloader.base.BaseDownloader._get_json")
    def test_no_response_raises(self, mock_get_json, tmp_path):
        mock_get_json.return_value = None

        with pytest.raises(RuntimeError, match="no response"):
            _downloader(tmp_path)._fetch_pairs("https://example.test/query")


class TestNameByCode:
    def test_one_name_per_code_first_sorted_wins(self):
        assert _name_by_code(PAIRS) == {
            "WAOWF": "Okanogan-Wenatchee National Forest",
            "CAYNP": "Yosemite National Park",
            "WANES": "Alpine Lakes Wilderness",
        }


class TestUnitNamesFile:
    def test_missing_file_returns_empty_map(self, tmp_path):
        assert _downloader(tmp_path)._load_unit_names() == {}

    def test_reads_the_lookup_csv(self, tmp_path):
        path = _write_lookup(tmp_path)

        assert NIFCDownloader(logger=MockLogger(), unit_names_file=path)._load_unit_names() == {
            "WAOWF": "Name of WAOWF",
            "CAYNP": "Name of CAYNP",
        }

    def test_blank_rows_are_skipped(self, tmp_path):
        output = tmp_path / "nifc_unit_names.csv"
        output.write_text("unit_code,unit_name\n,\nWAOWF,\nCAYNP,Yosemite\n")

        assert _downloader(tmp_path)._load_unit_names() == {"CAYNP": "Yosemite"}

    def test_writes_sorted_csv_and_creates_the_directory(self, tmp_path):
        dl = _downloader(tmp_path)
        dl.unit_names_file = str(tmp_path / "cache" / "nifc_unit_names.csv")

        dl._write_unit_names(_name_by_code(PAIRS))

        assert (tmp_path / "cache" / "nifc_unit_names.csv").read_text().splitlines() == [
            "unit_code,unit_name",
            "CAYNP,Yosemite National Park",
            "WANES,Alpine Lakes Wilderness",
            "WAOWF,Okanogan-Wenatchee National Forest",
        ]
        assert any("3 codes" in msg for _, msg in dl.logger.messages)

    def test_fetch_failure_writes_nothing(self, tmp_path, monkeypatch):
        dl = _downloader(tmp_path)

        def boom(api_url=...):
            raise RuntimeError("NIFC jurisdiction layer returned no code/name pairs — nothing written")

        monkeypatch.setattr(dl, "_fetch_pairs", boom)

        with pytest.raises(RuntimeError, match="no code/name pairs"):
            dl._unit_name_map({"WAOWF"})

        assert not os.path.exists(dl.unit_names_file)


class TestUnitNameMap:
    def test_lookup_hit_does_not_fetch(self, tmp_path, monkeypatch):
        path = _write_lookup(tmp_path)
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        monkeypatch.setattr(dl, "_fetch_pairs", lambda *args, **kwargs: pytest.fail("fetch not expected on a hit"))

        assert dl._unit_name_map({"WAOWF", "CAYNP"}) == {
            "WAOWF": "Name of WAOWF",
            "CAYNP": "Name of CAYNP",
        }

    def test_unknown_code_triggers_a_refresh(self, tmp_path):
        path = _write_lookup(tmp_path)
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        dl._fetch_pairs = lambda: PAIRS | {("ZZZZZ", "Fresh Name")}

        assert dl._unit_name_map({"WAOWF", "ZZZZZ"})["ZZZZZ"] == "Fresh Name"
        assert dl._load_unit_names()["WANES"] == "Alpine Lakes Wilderness"

    def test_unresolvable_code_is_dropped_not_raised(self, tmp_path):
        path = _write_lookup(tmp_path)
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        dl._fetch_pairs = lambda: {("WAOWF", "Name of WAOWF")}

        assert dl._unit_name_map({"WAOWF", "NVNV0100"}) == {"WAOWF": "Name of WAOWF"}

    def test_blank_codes_are_ignored(self, tmp_path, monkeypatch):
        path = _write_lookup(tmp_path, codes=("WAOWF",))
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        monkeypatch.setattr(
            dl, "_fetch_pairs", lambda *args, **kwargs: pytest.fail("blank codes must not trigger a fetch")
        )

        assert dl._unit_name_map({"", "   "}) == {}

    def test_missing_lookup_is_built(self, tmp_path):
        dl = _downloader(tmp_path)
        dl._fetch_pairs = lambda: PAIRS

        assert dl._unit_name_map({"WAOWF"}) == {"WAOWF": "Okanogan-Wenatchee National Forest"}
        assert os.path.exists(dl.unit_names_file)


class TestResolveUnitNames:
    def test_stamps_names_fallback_and_blank(self, tmp_path):
        path = _write_lookup(tmp_path)
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        dl._fetch_pairs = lambda: {("WAOWF", "Name of WAOWF"), ("CAYNP", "Name of CAYNP")}
        records = [
            {"jurisdiction_label": "WAOWF"},
            {"jurisdiction_label": "ZZUNK"},
            {"jurisdiction_label": ""},
            {"jurisdiction_label": None},
        ]

        dl._resolve_unit_names(records)

        assert [record["unit_name"] for record in records] == ["Name of WAOWF", "ZZUNK", "", ""]

    def test_logs_resolution_counts(self, tmp_path):
        path = _write_lookup(tmp_path, codes=("WAOWF",))
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)

        dl._resolve_unit_names([{"jurisdiction_label": "WAOWF"}])

        assert any("resolved 1 of 1 distinct codes" in msg for _, msg in dl.logger.messages)

    def test_empty_record_list_does_nothing(self, tmp_path):
        dl = _downloader(tmp_path)

        dl._resolve_unit_names([])

        assert not os.path.exists(dl.unit_names_file)

    @patch("downloader.base.BaseDownloader._get_json")
    def test_download_stamps_unit_name(self, mock_get_json, tmp_path):
        path = _write_lookup(tmp_path)
        dl = NIFCDownloader(logger=MockLogger(), unit_names_file=path)
        mock_get_json.return_value = {
            "features": [
                {
                    "attributes": {"poly_IncidentName": "Iron Fire", "attr_POOJurisdictionalUnit": "WAOWF"},
                    "centroid": {"x": -112.1, "y": 40.0},
                },
                {
                    "attributes": {"poly_IncidentName": "No Jurisdiction"},
                    "centroid": {"x": -110.0, "y": 39.0},
                },
            ]
        }

        records = dl.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))

        assert [record["unit_name"] for record in records] == ["Name of WAOWF", ""]
        keys = list(records[0].keys())
        assert keys[keys.index("jurisdiction_label") + 1] == "unit_name"

    @patch("downloader.base.BaseDownloader._get_json")
    def test_download_refreshes_the_lookup_for_an_unknown_code(self, mock_get_json, tmp_path):
        dl = _downloader(tmp_path)
        dl._fetch_pairs = lambda: {("WAOWF", "Fresh Name"), ("ZZUNK", "Fresh Code")}
        mock_get_json.return_value = {
            "features": [
                {"attributes": {"poly_IncidentName": "Fire", "attr_POOJurisdictionalUnit": "ZZUNK"}},
            ]
        }

        records = dl.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))

        assert records[0]["unit_name"] == "Fresh Code"
        assert dl._load_unit_names()["WAOWF"] == "Fresh Name"
