import csv
import datetime as dt
import json
import os
import tempfile
from unittest.mock import patch

import run_openmeteo_thresholds as script
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


def _create_downloader(rivers=None, logger=None, thresholds_file=None):
    if logger is None:
        logger = MockLogger()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(rivers or SAMPLE_RIVERS, f)
        temp_path = f.name
    try:
        return OpenMeteoFloodDownloader(logger=logger, rivers_file=temp_path, thresholds_file=thresholds_file)
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


def test_build_records_always_writes_the_ensemble_keys():
    """A response without ensemble arrays still produces the stable CSV keys."""
    downloader = _create_downloader()
    expected_keys = {
        "river_name",
        "country",
        "latitude",
        "longitude",
        "date",
        "discharge_m3s",
        *OpenMeteoFloodDownloader.ENSEMBLE_COLUMNS,
    }

    records = downloader._build_records(SAMPLE_RIVERS[0], SAMPLE_API_RESPONSE)

    assert records
    assert all(set(record) == expected_keys for record in records)
    assert all(record[column] is None for record in records for column in OpenMeteoFloodDownloader.ENSEMBLE_COLUMNS)


def test_build_records_keeps_ensemble_statistics_for_todays_forecast():
    """The forecast row carries the spread; the analysis row does not."""
    downloader = _create_downloader()
    response = {
        "daily": {
            "time": ["2026-09-01", "2026-09-02"],
            "river_discharge": [5500.0, 5620.0],
            "river_discharge_mean": [5500.0, 5650.0],
            "river_discharge_median": [5500.0, 5620.0],
            "river_discharge_p25": [5500.0, 5580.0],
            "river_discharge_p75": [5500.0, 5700.0],
        }
    }

    records = downloader._build_records(
        SAMPLE_RIVERS[0],
        response,
        analysis_date=dt.date(2026, 9, 1),
        today=dt.date(2026, 9, 1),
    )

    analysis, forecast = records
    assert analysis["discharge_mean_m3s"] is None
    assert analysis["discharge_p25_m3s"] is None
    assert forecast["discharge_mean_m3s"] == 5650.0
    assert forecast["discharge_median_m3s"] == 5620.0
    assert forecast["discharge_p25_m3s"] == 5580.0
    assert forecast["discharge_p75_m3s"] == 5700.0


def test_build_records_drops_ensemble_statistics_of_a_day_that_is_no_longer_a_forecast():
    """A backfill runs months later: the API now reports consolidated data."""
    downloader = _create_downloader()
    response = {
        "daily": {
            "time": ["2026-09-01", "2026-09-02"],
            "river_discharge": [5500.0, 5620.0],
            "river_discharge_mean": [5500.0, 5620.0],
            "river_discharge_p25": [5500.0, 5620.0],
        }
    }

    records = downloader._build_records(
        SAMPLE_RIVERS[0],
        response,
        analysis_date=dt.date(2026, 9, 1),
        today=dt.date(2026, 10, 6),
    )

    assert all(record[column] is None for record in records for column in ("discharge_mean_m3s", "discharge_p25_m3s"))


def test_build_records_without_a_reference_day_keeps_no_ensemble_statistics():
    """Without the analysis day every row would look like a forecast."""
    downloader = _create_downloader()
    response = {
        "daily": {
            "time": ["2026-09-02"],
            "river_discharge": [5620.0],
            "river_discharge_mean": [5650.0],
        }
    }

    (record,) = downloader._build_records(SAMPLE_RIVERS[0], response, today=dt.date(2026, 9, 1))

    assert record["discharge_mean_m3s"] is None


def test_query_river_requests_the_ensemble_variables():
    downloader = _create_downloader()
    seen: list[str] = []

    with patch.object(BaseDownloader, "_get_json", side_effect=lambda url: seen.append(url) or {}):
        downloader._query_river(
            "https://flood-api.open-meteo.com/v1/flood",
            SAMPLE_RIVERS[0],
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    (url,) = seen
    daily = url.split("daily=")[1].split("&")[0]
    expected = ["river_discharge", *(f"river_discharge_{var}" for var in OpenMeteoFloodDownloader.ENSEMBLE_VARS)]
    assert daily.split(",") == expected


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


def _baseline_response(days: int = 36, start: dt.date = dt.date(2026, 9, 1), value: float = 1000.0) -> dict:
    """A baseline long enough for the default minimum, climbing one unit a day."""
    return {
        "daily": {
            "time": [(start + dt.timedelta(days=index)).isoformat() for index in range(days)],
            "river_discharge": [value + index for index in range(days)],
        }
    }


def _stub_fetcher(monkeypatch, answer=None) -> dict:
    """Replace the throttled fetcher with one answering every river from *answer*.

    Returns what the build asked the fetcher for — ``answer=None`` makes every
    river fail, the way an unreachable API would.
    """
    captured: dict = {}

    def _make_fetcher(_downloader, api_url, start, end, _logger, sleep=1.0, max_hour_waits=6):
        captured.update(api_url=api_url, start=start, end=end, sleep=sleep, max_hour_waits=max_hour_waits)
        return lambda river: answer() if callable(answer) else answer

    monkeypatch.setattr(script, "make_fetcher", _make_fetcher)
    return captured


class TestEnsureAuxiliaryFiles:
    """The download keeps GEO_ETL's threshold reference present."""

    def test_missing_reference_is_built_from_the_default_baseline(self, tmp_path, monkeypatch):
        logger = MockLogger()
        output = tmp_path / "openmeteo_discharge_thresholds.csv"
        downloader = _create_downloader(logger=logger, thresholds_file=str(output))
        captured = _stub_fetcher(monkeypatch, _baseline_response)

        downloader.ensure_auxiliary_files("https://flood-api.test/v1/flood")

        with open(output, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert list(rows[0]) == list(script.FIELDNAMES)
        assert len(rows) == len(SAMPLE_RIVERS)
        assert rows[0]["river_name"] == "Danube"
        assert rows[0]["baseline_start"] == "2026-09-01"
        assert rows[0]["baseline_end"] == "2026-10-06"
        assert float(rows[0]["discharge_p95_m3s"]) == 1033.25
        assert captured["api_url"] == "https://flood-api.test/v1/flood"
        assert captured["start"] == dt.datetime(2026, 9, 1)
        assert captured["end"] == dt.datetime.strptime(dt.date.today().isoformat(), "%Y-%m-%d")
        assert captured["max_hour_waits"] == 1
        assert any("missing" in msg and "building it" in msg for _, msg in logger.messages)

    def test_an_empty_remnant_of_a_crashed_write_is_rebuilt(self, tmp_path, monkeypatch):
        logger = MockLogger()
        output = tmp_path / "openmeteo_discharge_thresholds.csv"
        output.write_bytes(b"")
        downloader = _create_downloader(logger=logger, thresholds_file=str(output))
        _stub_fetcher(monkeypatch, _baseline_response)

        downloader.ensure_auxiliary_files("https://flood-api.test/v1/flood")

        with open(output, newline="", encoding="utf-8") as handle:
            assert len(list(csv.DictReader(handle))) == len(SAMPLE_RIVERS)

    def test_a_present_reference_is_left_alone(self, tmp_path, monkeypatch):
        logger = MockLogger()
        output = tmp_path / "openmeteo_discharge_thresholds.csv"
        written = "river_name,country,discharge_p95_m3s\nAmazon,Brazil,100.0\n"
        output.write_text(written)
        downloader = _create_downloader(logger=logger, thresholds_file=str(output))

        def _fail(*_args, **_kwargs):
            raise AssertionError("make_fetcher must not run when the reference is already there")

        monkeypatch.setattr(script, "make_fetcher", _fail)

        downloader.ensure_auxiliary_files("https://flood-api.test/v1/flood")

        assert output.read_text() == written
        assert any("already present" in msg for _, msg in logger.messages)

    def test_an_unreachable_api_leaves_the_reference_unwritten(self, tmp_path, monkeypatch):
        logger = MockLogger()
        output = tmp_path / "openmeteo_discharge_thresholds.csv"
        downloader = _create_downloader(logger=logger, thresholds_file=str(output))
        _stub_fetcher(monkeypatch)

        downloader.ensure_auxiliary_files("https://flood-api.test/v1/flood")

        assert not output.exists()
        assert any(level == "ERROR" and "left unwritten" in msg for level, msg in logger.messages)
