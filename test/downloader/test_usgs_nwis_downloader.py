from __future__ import annotations

import csv
import datetime as dt
from typing import Any
from unittest.mock import patch

import pytest

from downloader.base import BaseDownloader
from downloader.usgs_nwis import FLOOD_CATEGORY_COLUMNS, NO_FLOODING, USGSNWISDownloader
from test.downloader.conftest import MockLogger

IGNORED_URL = "https://ignored.com"
IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
DATE_RANGE = (dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))


def _reading(value: Any, date: str, qualifiers: tuple[str, ...] = ("P",)) -> dict[str, Any]:
    return {"value": value, "qualifiers": list(qualifiers), "dateTime": f"{date}T00:00:00.000-04:00"}


def _series(
    site_code: str,
    site_name: str,
    parameter: str,
    unit: str,
    latitude: float,
    longitude: float,
    readings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "sourceInfo": {
            "siteName": site_name,
            "siteCode": [{"value": site_code, "network": "NWIS", "agencyCode": "USGS"}],
            "geoLocation": {"geogLocation": {"srs": "EPSG:4326", "latitude": latitude, "longitude": longitude}},
        },
        "variable": {
            "variableCode": [{"value": parameter}],
            "variableName": parameter,
            "unit": {"unitCode": unit},
        },
        "values": [{"value": readings}],
    }


POTOMAC = "POTOMAC RIVER NEAR WASH, DC"
HUDSON = "HUDSON RIVER AT N TROY, NY"

SAMPLE_API_RESPONSE: dict[str, Any] = {
    "value": {
        "timeSeries": [
            _series(
                "01646500",
                POTOMAC,
                "00060",
                "ft3/s",
                38.94977778,
                -77.12763889,
                [_reading("2320", "2026-09-01"), _reading("2220", "2026-09-02"), _reading("2300", "2026-09-02")],
            ),
            _series(
                "01646500",
                POTOMAC,
                "00065",
                "ft",
                38.94977778,
                -77.12763889,
                [_reading("2.5", "2026-09-01"), _reading("2.91", "2026-09-01"), _reading("5.5", "2026-09-02")],
            ),
            _series(
                "01358000",
                HUDSON,
                "00060",
                "ft3/s",
                42.75,
                -73.68,
                [_reading("8500", "2026-09-01")],
            ),
        ]
    }
}

SAMPLE_API_RESPONSE_WITH_NON_NUMERIC: dict[str, Any] = {
    "value": {
        "timeSeries": [
            _series(
                "01646500",
                POTOMAC,
                "00060",
                "ft3/s",
                38.94977778,
                -77.12763889,
                [_reading("Ice", "2026-09-01"), _reading("Eqp", "2026-09-01")],
            ),
        ]
    }
}

GAUGE_RESPONSE: dict[str, Any] = {
    "lid": "BRKM2",
    "usgsId": "01646500",
    "name": "Potomac River near Washington DC (Little Falls)",
    "state": {"abbreviation": "MD", "name": "Maryland"},
    "latitude": 38.949722222222,
    "longitude": -77.127777777778,
    "flood": {
        "stageUnits": "ft",
        "flowUnits": "cfs",
        "categories": {
            "action": {"stage": 5, "flow": 22000},
            "minor": {"stage": 10, "flow": -9999},
            "moderate": {"stage": 12, "flow": -9999},
            "major": {"stage": 14, "flow": -9999},
        },
    },
}


@pytest.fixture(autouse=True)
def _flood_categories_file(tmp_path, monkeypatch):
    """Keep every downloader's reference in the test's own tmp folder."""
    monkeypatch.setattr(USGSNWISDownloader, "DEFAULT_FLOOD_CATEGORIES_FILE", str(tmp_path / "flood_categories.csv"))


def _create_downloader(**kwargs) -> USGSNWISDownloader:
    kwargs.setdefault("logger", MockLogger())
    return USGSNWISDownloader(**kwargs)


def _mock_json(nwis: dict[str, Any], gauges: dict[str, dict[str, Any]] | None = None):
    """Route ``_get_json`` by URL: NWIS for the water service, per site for NWPS."""
    gauges = gauges or {}

    def _get(url: str):
        if "/gauges/" in url:
            return next((payload for site, payload in gauges.items() if f"/gauges/{site}" in url), None)
        return nwis

    return _get


def _write_reference(path, stages: dict[str, str] | None = None) -> None:
    row = {
        "site_id": "USGS-01646500",
        "identifier": "BRKM2",
        "site_name": "Potomac River near Washington DC (Little Falls)",
        "state": "MD",
        "latitude": "38.949722222222",
        "longitude": "-77.127777777778",
        **{f"{level}_stage_ft": (stages or {}).get(level, "") for level in ("action", "minor", "moderate", "major")},
    }
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FLOOD_CATEGORY_COLUMNS))
        writer.writeheader()
        writer.writerow(row)


def _read_reference(path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_build_url():
    downloader = _create_downloader()

    url = downloader._build_url(
        "https://waterservices.usgs.gov/nwis/iv/",
        dt.datetime(2026, 9, 1),
        dt.datetime(2026, 9, 14),
    )

    assert "sites=01646500" in url
    assert "parameterCd=00060,00065" in url
    assert "startDT=2026-09-01" in url
    assert "endDT=2026-09-14" in url
    assert "format=json" in url


def test_build_url_without_stage_parameter():
    downloader = _create_downloader(stage_parameter_code="")

    url = downloader._build_url(IV_URL, *DATE_RANGE)

    assert "parameterCd=00060" in url
    assert "00065" not in url


def test_build_records_aggregates_the_day():
    downloader = _create_downloader()

    records = downloader._build_records(SAMPLE_API_RESPONSE)

    assert [record["date"] for record in records] == ["2026-09-01", "2026-09-01", "2026-09-02"]
    assert [record["site_id"] for record in records] == [
        "USGS-01358000",
        "USGS-01646500",
        "USGS-01646500",
    ]
    potomac_first_day = records[1]
    assert potomac_first_day["site_name"] == POTOMAC
    assert potomac_first_day["parameter_code"] == "00060"
    assert potomac_first_day["value"] == "2320"
    assert potomac_first_day["unit"] == "ft3/s"
    assert potomac_first_day["qualifiers"] == "P"
    assert potomac_first_day["gauge_height"] == "2.91"
    assert potomac_first_day["latitude"] == 38.94977778
    assert potomac_first_day["longitude"] == -77.12763889
    assert list(potomac_first_day) == [
        "site_id",
        "site_name",
        "parameter_code",
        "date",
        "value",
        "unit",
        "qualifiers",
        "gauge_height",
        "flood_category",
        "latitude",
        "longitude",
    ]


def test_build_records_averages_the_readings_of_the_day():
    downloader = _create_downloader()

    records = downloader._build_records(SAMPLE_API_RESPONSE)

    second_day = records[2]
    assert second_day["date"] == "2026-09-02"
    assert second_day["value"] == "2260"
    assert second_day["gauge_height"] == "5.5"


def test_build_records_without_a_stage_series_keeps_the_height_empty():
    downloader = _create_downloader()

    records = downloader._build_records(SAMPLE_API_RESPONSE)

    assert records[0]["site_id"] == "USGS-01358000"
    assert records[0]["gauge_height"] == ""
    assert records[0]["flood_category"] == ""


def test_build_records_skips_days_without_numeric_readings():
    downloader = _create_downloader()

    assert downloader._build_records(SAMPLE_API_RESPONSE_WITH_NON_NUMERIC) == []


def test_build_records_writes_one_row_per_configured_parameter():
    response = {
        "value": {
            "timeSeries": [
                _series(
                    "01646500",
                    POTOMAC,
                    "00060",
                    "ft3/s",
                    38.94977778,
                    -77.12763889,
                    [_reading("2320", "2026-09-01")],
                ),
                _series(
                    "01646500",
                    POTOMAC,
                    "00063",
                    "degC",
                    38.94977778,
                    -77.12763889,
                    [_reading("12.5", "2026-09-01")],
                ),
            ]
        }
    }
    downloader = _create_downloader(parameter_code="00060,00063")

    records = downloader._build_records(response)

    assert [(record["parameter_code"], record["value"], record["unit"]) for record in records] == [
        ("00060", "2320", "ft3/s"),
        ("00063", "12.5", "degC"),
    ]


def test_download_by_date_range_labels_the_peak_stage(tmp_path):
    logger = MockLogger()
    reference = tmp_path / "flood_categories.csv"
    downloader = USGSNWISDownloader(logger=logger, flood_categories_file=str(reference))

    with patch.object(
        BaseDownloader,
        "_get_json",
        side_effect=_mock_json(SAMPLE_API_RESPONSE, {"01646500": GAUGE_RESPONSE}),
    ):
        records = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    assert [(record["gauge_height"], record["flood_category"]) for record in records] == [
        ("", ""),
        ("2.91", NO_FLOODING),
        ("5.5", "action"),
    ]
    assert all(record["geocode_state"] == "MT" for record in records)

    rows = _read_reference(reference)
    assert list(rows[0]) == list(FLOOD_CATEGORY_COLUMNS)
    assert rows[0]["site_id"] == "USGS-01646500"
    assert rows[0]["identifier"] == "BRKM2"
    assert rows[0]["state"] == "MD"
    assert rows[0]["action_stage_ft"] == "5"
    assert rows[0]["minor_stage_ft"] == "10"
    assert rows[0]["moderate_stage_ft"] == "12"
    assert rows[0]["major_stage_ft"] == "14"


def test_download_by_date_range_empty():
    logger = MockLogger()
    downloader = _create_downloader(logger=logger)

    with patch.object(BaseDownloader, "_get_json", return_value={"value": {"timeSeries": []}}):
        result = downloader.download_by_date_range(IGNORED_URL, *DATE_RANGE)

    assert result == []


def test_download_by_date_range_no_data():
    logger = MockLogger()
    downloader = _create_downloader(logger=logger)

    with patch.object(BaseDownloader, "_get_json", return_value=None):
        result = downloader.download_by_date_range(IGNORED_URL, *DATE_RANGE)

    assert result == []


@pytest.mark.parametrize(
    ("gauge_height", "expected"),
    [
        ("4.99", NO_FLOODING),
        ("5", "action"),
        ("9.99", "action"),
        ("10", "minor"),
        ("11.99", "minor"),
        ("12", "moderate"),
        ("13.99", "moderate"),
        ("14", "major"),
        ("28.1", "major"),
    ],
)
def test_flood_category_follows_the_nws_thresholds(tmp_path, gauge_height, expected):
    reference = tmp_path / "flood_categories.csv"
    _write_reference(reference, {"action": "5", "minor": "10", "moderate": "12", "major": "14"})
    downloader = USGSNWISDownloader(logger=MockLogger(), flood_categories_file=str(reference))

    assert downloader._flood_category("USGS-01646500", gauge_height) == expected


def test_flood_category_is_empty_without_a_usable_answer(tmp_path):
    reference = tmp_path / "flood_categories.csv"
    _write_reference(reference)
    downloader = USGSNWISDownloader(logger=MockLogger(), flood_categories_file=str(reference))

    assert downloader._flood_category("USGS-01646500", "") == ""
    assert downloader._flood_category("USGS-99999999", "15") == ""
    assert downloader._flood_category("USGS-01646500", "not-a-number") == ""


def test_flood_category_is_empty_when_the_gauge_defines_no_threshold(tmp_path):
    reference = tmp_path / "flood_categories.csv"
    _write_reference(reference, {"action": "", "minor": "", "moderate": "", "major": ""})
    downloader = USGSNWISDownloader(logger=MockLogger(), flood_categories_file=str(reference))

    assert downloader._flood_category("USGS-01646500", "15") == ""


@pytest.mark.parametrize(
    ("stage", "expected"),
    [(5, "5"), (5.5, "5.5"), (2.85, "2.85"), (0, "0"), (-9999, ""), (None, ""), ("", ""), ("Ice", "")],
)
def test_stage_text_marks_undefined_thresholds_empty(stage, expected):
    assert USGSNWISDownloader._stage_text(stage) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2320.0, "2320"), (2233.6805555555555, "2233.68"), (5.5, "5.5"), (100.0, "100"), (0.0, "0"), (2.006, "2.01")],
)
def test_format_number_drops_the_trailing_zeros(value, expected):
    assert USGSNWISDownloader._format_number(value) == expected


def test_ensure_auxiliary_files_builds_the_reference(tmp_path):
    reference = tmp_path / "flood_categories.csv"
    downloader = USGSNWISDownloader(logger=MockLogger(), flood_categories_file=str(reference))

    with patch.object(BaseDownloader, "_get_json", side_effect=_mock_json({}, {"01646500": GAUGE_RESPONSE})):
        downloader.ensure_auxiliary_files("https://waterservices.usgs.gov/nwis/iv/")

    assert [row["site_id"] for row in _read_reference(reference)] == ["USGS-01646500"]


def test_ensure_auxiliary_files_keeps_an_existing_reference(tmp_path):
    reference = tmp_path / "flood_categories.csv"
    _write_reference(reference, {"action": "7"})
    downloader = USGSNWISDownloader(logger=MockLogger(), flood_categories_file=str(reference))

    with patch.object(BaseDownloader, "_get_json", side_effect=AssertionError("must not query NWPS")):
        downloader.ensure_auxiliary_files("https://waterservices.usgs.gov/nwis/iv/")

    assert _read_reference(reference)[0]["action_stage_ft"] == "7"


def test_ensure_auxiliary_files_leaves_the_reference_unwritten_when_nwps_is_down(tmp_path):
    reference = tmp_path / "flood_categories.csv"
    logger = MockLogger()
    downloader = USGSNWISDownloader(logger=logger, flood_categories_file=str(reference))

    with patch.object(BaseDownloader, "_get_json", return_value=None):
        downloader.ensure_auxiliary_files("https://waterservices.usgs.gov/nwis/iv/")

    assert not reference.exists()
    assert any("No data received from NWS NWPS API" in message for _, message in logger.messages)


def test_download_stamps_geocode_state():
    """Every gauge point is reverse-geocoded into geocode_state."""
    downloader = _create_downloader()

    with patch.object(BaseDownloader, "_get_json", return_value=SAMPLE_API_RESPONSE):
        result = downloader.download_by_date_range(IGNORED_URL, *DATE_RANGE)

    assert len(result) == 3
    assert all(record["geocode_state"] == "MT" for record in result)
    assert "geocode_country" not in result[0]
