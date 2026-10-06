import csv
import datetime as dt
import sys

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

import run_openmeteo_thresholds as script
from model import SourceConfig
from run_openmeteo_thresholds import (
    FIELDNAMES,
    _baseline_url,
    build_row,
    build_thresholds,
    make_fetcher,
    percentile,
    read_thresholds,
    write_thresholds,
)
from test.downloader.conftest import MockLogger

RIVER = {"name": "Amazon", "country": "Brazil", "latitude": -3.14, "longitude": -59.98}

BASELINE_DAYS = 400


def _response(values: list[float | None], start: dt.date = dt.date(2026, 1, 1)) -> dict:
    return {
        "daily": {
            "time": [(start + dt.timedelta(days=index)).isoformat() for index in range(len(values))],
            "river_discharge": values,
        }
    }


def _baseline(values: float = 1000.0) -> list[float]:
    """A *BASELINE_DAYS* long series climbing from ``values`` to ``values * 2``."""
    return [values + index for index in range(BASELINE_DAYS)]


class TestPercentile:
    def test_interpolates_between_two_samples(self):
        assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5

    def test_returns_an_observed_value_for_the_edges(self):
        assert percentile([5.0, 7.0, 9.0], 0.0) == 5.0
        assert percentile([5.0, 7.0, 9.0], 1.0) == 9.0

    def test_single_sample_is_its_own_percentile(self):
        assert percentile([42.0], 0.95) == 42.0


class TestBuildRow:
    def test_row_carries_identity_counts_and_percentiles(self):
        row = build_row(RIVER, _response(_baseline()), min_days=365)

        assert row is not None
        assert row["river_name"] == "Amazon"
        assert row["country"] == "Brazil"
        assert row["latitude"] == -3.14
        assert row["longitude"] == -59.98
        assert row["baseline_days"] == BASELINE_DAYS
        assert row["baseline_start"] == "2026-01-01"
        assert row["baseline_end"] == (dt.date(2026, 1, 1) + dt.timedelta(days=BASELINE_DAYS - 1)).isoformat()
        assert list(row) == FIELDNAMES
        assert row["discharge_p50_m3s"] <= row["discharge_p90_m3s"]
        assert row["discharge_p90_m3s"] <= row["discharge_p95_m3s"]
        assert row["discharge_p95_m3s"] <= row["discharge_p99_m3s"]

    def test_null_days_do_not_count_towards_the_baseline(self):
        values: list[float | None] = [None] * 10 + _baseline()[10:]

        row = build_row(RIVER, _response(values), min_days=365)

        assert row is not None
        assert row["baseline_days"] == BASELINE_DAYS - 10
        assert row["baseline_start"] == "2026-01-11"

    def test_river_below_the_minimum_length_is_skipped(self):
        assert build_row(RIVER, _response(_baseline()[:100]), min_days=365) is None

    def test_empty_response_is_skipped(self):
        assert build_row(RIVER, _response([]), min_days=365) is None


class TestBuildThresholds:
    class _FakeDownloader:
        def __init__(self, responses):
            self._rivers = [{"name": name, "country": "X", "latitude": 0.0, "longitude": 0.0} for name in responses]
            self._responses = responses
            self.queries: list[str] = []

        def _query_river(self, api_url, river, start, end):
            self.queries.append(f"{river['name']}:{start.date()}..{end.date()}")
            return self._responses[river["name"]]

    def test_keeps_usable_rivers_in_order_and_skips_the_rest(self):
        responses = {
            "R0": _response(_baseline()),
            "R1": _response([]),
            "R2": _response(_baseline(2000.0)),
        }
        downloader = self._FakeDownloader(responses)

        rows = build_thresholds(
            downloader,  # type: ignore[arg-type]
            "https://example.com",
            "2026-01-01",
            "2026-02-05",
            365,
            MockLogger(),
        )

        assert [row["river_name"] for row in rows] == ["R0", "R2"]
        assert rows[1]["discharge_p99_m3s"] > rows[0]["discharge_p99_m3s"]

    def test_queries_the_baseline_range_once_per_river(self):
        downloader = self._FakeDownloader({"R0": _response(_baseline())})
        logger = MockLogger()

        rows = build_thresholds(downloader, "https://example.com", "2026-01-01", "2026-01-02", 365, logger)

        assert downloader.queries == ["R0:2026-01-01..2026-01-02"]
        assert len(rows) == 1
        assert [level for level, _ in logger.messages] == ["INFO", "INFO"]


class TestWriteThresholds:
    def test_writes_the_header_even_without_rows(self, tmp_path):
        output = tmp_path / "thresholds.csv"

        write_thresholds([], str(output))

        assert output.read_text().splitlines() == [",".join(FIELDNAMES)]

    def test_writes_one_line_per_row(self, tmp_path):
        output = tmp_path / "thresholds.csv"
        row = build_row(RIVER, _response(_baseline()), min_days=365)

        write_thresholds([row], str(output))

        with open(output, newline="", encoding="utf-8") as handle:
            records = list(csv.DictReader(handle))
        assert len(records) == 1
        assert records[0]["river_name"] == "Amazon"
        assert float(records[0]["discharge_p95_m3s"]) >= float(records[0]["discharge_p90_m3s"])


NILE = {"name": "Nile", "country": "Egypt", "latitude": 0.0, "longitude": 0.0}


class _ListDownloader:
    """River list plus a recording stand-in for the API."""

    def __init__(self, rivers: list[dict]) -> None:
        self._rivers = rivers
        self.queries: list[str] = []

    def _query_river(self, api_url, river, start, end):
        self.queries.append(river["name"])
        return _response(_baseline(3000.0))


class _ScriptedResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RequestsConnectionError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._payload or {}


class _ScriptedSession:
    """Answers the next scripted response, repeating the last one when exhausted."""

    def __init__(self, responses: list) -> None:
        self._responses = responses
        self.requests: list[str] = []

    def mount(self, prefix, adapter) -> None:
        return None

    def get(self, url: str, timeout: int | None = None) -> object:
        self.requests.append(url)
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


class _SessionDownloader:
    def __init__(self, session) -> None:
        self.session = session
        self.timeout = 30


class TestBaselineUrl:
    def test_asks_for_the_discharge_series_alone(self):
        url = _baseline_url("https://flood.example/v1", RIVER, dt.datetime(1984, 1, 1), dt.datetime(2026, 10, 6))

        assert url == (
            "https://flood.example/v1?latitude=-3.14&longitude=-59.98"
            "&daily=river_discharge&start_date=1984-01-01&end_date=2026-10-06"
        )


class TestReadThresholds:
    def test_a_missing_file_resumes_from_nothing(self, tmp_path):
        assert read_thresholds(str(tmp_path / "thresholds.csv")) == []

    def test_reads_the_written_rows_back(self, tmp_path):
        output = tmp_path / "thresholds.csv"
        write_thresholds([build_row(RIVER, _response(_baseline()), min_days=365)], str(output))

        rows = read_thresholds(str(output))

        assert len(rows) == 1
        assert rows[0]["river_name"] == "Amazon"
        assert rows[0]["baseline_days"] == str(BASELINE_DAYS)

    def test_a_truncated_last_line_is_dropped(self, tmp_path):
        output = tmp_path / "thresholds.csv"
        write_thresholds([build_row(RIVER, _response(_baseline()), min_days=365)], str(output))
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("Paraná,Brazil,-25.0,-54.0,1000,2026-01-01,20")

        rows = read_thresholds(str(output))

        assert [row["river_name"] for row in rows] == ["Amazon"]

    def test_a_file_with_other_columns_is_rejected(self, tmp_path):
        output = tmp_path / "thresholds.csv"
        output.write_text("foo,bar\n1,2\n", encoding="utf-8")

        with pytest.raises(ValueError, match="columns"):
            read_thresholds(str(output))


class TestResume:
    def test_rivers_already_on_disk_are_not_fetched_again(self):
        existing = build_row(RIVER, _response(_baseline()), min_days=365)
        downloader = _ListDownloader([RIVER, NILE])
        written: list[int] = []

        rows = build_thresholds(
            downloader,  # type: ignore[arg-type]
            "https://example.com",
            "2026-01-01",
            "2026-01-02",
            365,
            MockLogger(),
            existing=[existing],
            on_row=lambda current: written.append(len(current)),
        )

        assert downloader.queries == ["Nile"]
        assert [row["river_name"] for row in rows] == ["Amazon", "Nile"]
        assert written == [2]


class TestMakeFetcher:
    @staticmethod
    def _fetcher(responses: list, monkeypatch: pytest.MonkeyPatch, **kwargs):
        session = _ScriptedSession(responses)
        waits: list[float] = []
        pauses: list[float] = []
        monkeypatch.setattr(script, "_seconds_until_next_hour", lambda: waits.append(7.0) or 7.0)
        monkeypatch.setattr(script.time, "sleep", lambda seconds: pauses.append(seconds))
        fetch = make_fetcher(
            _SessionDownloader(session),  # type: ignore[arg-type]
            "https://example.com",
            dt.datetime(1984, 1, 1),
            dt.datetime(2026, 1, 1),
            MockLogger(),
            **kwargs,
        )
        return fetch, session, waits, pauses

    def test_answers_with_the_payload_and_paces_itself(self, monkeypatch):
        payload = {"daily": {"time": [], "river_discharge": []}}
        fetch, session, waits, pauses = self._fetcher([_ScriptedResponse(200, payload)], monkeypatch)

        assert fetch(RIVER) == payload
        assert len(session.requests) == 1
        assert waits == []
        assert pauses == [1.0]

    def test_waits_out_the_hourly_limit_and_retries(self, monkeypatch):
        payload = {"daily": {"time": []}}
        responses = [_ScriptedResponse(429), _ScriptedResponse(200, payload)]
        fetch, session, waits, pauses = self._fetcher(responses, monkeypatch)

        assert fetch(RIVER) == payload
        assert len(session.requests) == 2
        assert waits == [7.0]
        assert pauses == [7.0, 1.0]

    def test_gives_up_once_the_limit_persists(self, monkeypatch):
        fetch, session, waits, _ = self._fetcher([_ScriptedResponse(429)], monkeypatch, max_hour_waits=1)

        assert fetch(RIVER) is None
        assert len(session.requests) == 2
        assert waits == [7.0, 7.0]

    def test_network_errors_are_reported_as_none(self, monkeypatch):
        fetch, _, _, pauses = self._fetcher([RequestsConnectionError("boom")], monkeypatch)

        assert fetch(RIVER) is None
        assert pauses == []


class TestParseArgs:
    """The two file paths come from ``params`` of the OpenMeteo_Flood source."""

    @staticmethod
    def _source(params: dict | None = None) -> SourceConfig:
        return SourceConfig(
            type="openmeteo_flood",
            enabled=True,
            api_url="https://flood-api.test/v1/flood",
            start_date="2026-09-01",
            output_folder="data/OpenMeteo_Flood",
            output_file_pattern="openmeteo_rivers_{date}.csv",
            params=params or {},
        )

    def test_the_paths_come_from_the_source_params(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_openmeteo_thresholds.py"])
        output = str(tmp_path / "thresholds.csv")
        rivers = str(tmp_path / "rivers.json")

        args = script.parse_args(self._source({"rivers_file": rivers, "thresholds_file": output}))

        assert args.output == output
        assert args.rivers_file == rivers

    def test_the_paths_fall_back_to_the_documented_defaults(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_openmeteo_thresholds.py"])

        args = script.parse_args(self._source())

        assert args.output == script.DEFAULT_OUTPUT
        assert args.rivers_file == script.DEFAULT_RIVERS_FILE
        assert args.baseline_start == script.DEFAULT_BASELINE_START
        assert args.min_days == script.DEFAULT_MIN_DAYS
        assert args.sleep == script.DEFAULT_SLEEP
