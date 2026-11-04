import datetime as dt
import signal
import time
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


def _mock_csv_response(text: str = SAMPLE_CSV) -> MagicMock:
    """Mock a streaming requests response that yields the CSV in one chunk."""
    response = MagicMock()
    response.iter_content.return_value = [text.encode()]
    response.raise_for_status = MagicMock()
    response.close = MagicMock()
    return response


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
    ("kwargs", "attribute", "expected"),
    [
        ({"geocode_distance_km": 50}, "_geocode_distance_km", 50),
        ({"download_timeout": 120}, "_download_timeout", 120),
        ({"download_chunk_size": 65536}, "_download_chunk_size", 65536),
        ({"download_attempts": 5}, "_download_attempts", 5),
        ({"download_retry_backoff_seconds": 1.5}, "_retry_backoff_seconds", 1.5),
        ({"progress_log_bytes": 4096}, "_progress_log_bytes", 4096),
    ],
    ids=[
        "geocode-distance",
        "download-timeout",
        "download-chunk-size",
        "download-attempts",
        "retry-backoff",
        "progress-log-bytes",
    ],
)
def test_operational_knobs_are_taken_from_config(kwargs, attribute, expected):
    """Every tunable IBTrACS knob is a constructor argument populated from config.json params."""
    downloader = IBTrACSDownloader(logger=MockLogger(), **kwargs)

    assert getattr(downloader, attribute) == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"geocode_distance_km": 0},
        {"download_timeout": 0},
        {"download_chunk_size": 0},
        {"download_attempts": 0},
        {"download_retry_backoff_seconds": 0},
        {"progress_log_bytes": 0},
    ],
    ids=[
        "geocode-distance",
        "download-timeout",
        "download-chunk-size",
        "download-attempts",
        "retry-backoff",
        "progress-log-bytes",
    ],
)
def test_non_positive_operational_knobs_are_rejected(kwargs):
    """A zero/negative tunable fails at construction instead of disabling the safeguard."""
    name = next(iter(kwargs))

    with pytest.raises(ValueError, match=f"{name} must be positive"):
        IBTrACSDownloader(logger=MockLogger(), **kwargs)


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

    with patch.object(downloader.session, "get", return_value=_mock_csv_response()) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    assert [record["ISO_TIME"] for record in result] == expected_times
    called_url = mock_get.call_args[0][0]
    assert "ibtracs.last3years.list.v04r01.csv" in called_url
    assert mock_get.call_args.kwargs["stream"] is True


@pytest.mark.parametrize(
    ("csv_text", "end_date", "expected_times", "expected_sid"),
    [
        (
            SAMPLE_CSV,
            dt.datetime(2026, 9, 3),
            ["2026-09-01 06:00:00", "2026-09-01 12:00:00", "2026-09-02 06:00:00", "2026-09-01 18:00:00"],
            None,
        ),
        (
            "SID,ISO_TIME,BASIN,SEASON,NAME\n"
            " , , ,Year, \n"
            "2026001NA01,2026-09-01 06:00:00,NA,2026,GAMMA\n"
            "2026001NA01,2026-09-05 06:00:00,NA,2026,GAMMA\n",
            dt.datetime(2026, 9, 2),
            ["2026-09-01 06:00:00"],
            "2026001NA01",
        ),
    ],
    ids=["units-row-skipped", "iso-time-resolved-by-name"],
)
def test_download_parses_csv_by_header(csv_text, end_date, expected_times, expected_sid):
    """The units row is skipped and ISO_TIME is located by header name, not by position."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    with patch.object(downloader.session, "get", return_value=_mock_csv_response(csv_text)):
        result = downloader.download_by_date_range("https://example.com/api", dt.datetime(2026, 9, 1), end_date)

    assert [record["ISO_TIME"] for record in result] == expected_times
    assert all(record["SEASON"] != "Year" for record in result)
    if expected_sid is not None:
        assert result[0]["SID"] == expected_sid


@pytest.mark.parametrize(
    ("csv_text", "expected_log"),
    [
        ("SID,SEASON,BASIN\n ,Year,NA\n", "has no ISO_TIME column"),
        ("SID,SEASON,ISO_TIME\n ,Year, \n", None),
    ],
    ids=["missing-iso-time", "empty"],
)
def test_download_by_date_range_unusable_csv(csv_text, expected_log):
    """A header without ISO_TIME fails loudly; an otherwise empty CSV returns no records."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    with patch.object(downloader.session, "get", return_value=_mock_csv_response(csv_text)):
        result = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )

    assert result == []
    if expected_log is not None:
        assert any(expected_log in msg for _, msg in logger.messages)


def test_download_by_date_range_custom_dataset():
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger, dataset="all")

    start_date = dt.datetime(2026, 9, 1)
    end_date = dt.datetime(2026, 9, 2)

    with patch.object(downloader.session, "get", return_value=_mock_csv_response()) as mock_get:
        result = downloader.download_by_date_range("https://example.com/api", start_date, end_date)

    called_url = mock_get.call_args[0][0]
    assert "ibtracs.all.list.v04r01.csv" in called_url
    assert len(result) == 3


def test_download_reuses_the_dataset_for_later_days():
    """A multi-day run downloads the upstream CSV once and filters every day from it."""
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    with patch.object(downloader.session, "get", return_value=_mock_csv_response()) as mock_get:
        first = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )
        second = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 2), dt.datetime(2026, 9, 3)
        )

    assert mock_get.call_count == 1
    assert len(first) == 3
    assert [record["ISO_TIME"] for record in second] == ["2026-09-02 06:00:00"]
    assert any("already downloaded in this run" in msg for _, msg in logger.messages)


@pytest.mark.parametrize(
    ("failure_mode", "expected_calls", "expected_rows"),
    [
        ("http-error", 3, 0),
        ("connection-error", 3, 0),
        ("stalled-stream", 2, 3),
    ],
    ids=["http-error", "connection-error", "stalled-stream"],
)
def test_download_retries_transient_failures(failure_mode, expected_calls, expected_rows, monkeypatch):
    """HTTP/network errors exhaust the bounded retries; a stalled stream can recover on retry."""
    monkeypatch.setattr("downloader.ibtracs.time.sleep", lambda _seconds: None)
    logger = MockLogger()
    downloader = IBTrACSDownloader(logger=logger)

    if failure_mode == "http-error":
        response = MagicMock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        get_patcher = patch.object(downloader.session, "get", return_value=response)
    elif failure_mode == "connection-error":
        get_patcher = patch.object(
            downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")
        )
    else:
        stalled = MagicMock()
        stalled.raise_for_status = MagicMock()
        stalled.close = MagicMock()

        def broken_chunks(*_args, **_kwargs):
            yield b"SID,SEASON,ISO_TIME\n"
            raise requests.exceptions.ChunkedEncodingError("connection broken")

        stalled.iter_content.side_effect = broken_chunks
        get_patcher = patch.object(downloader.session, "get", side_effect=[stalled, _mock_csv_response()])

    with get_patcher as mock_get:
        result = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2)
        )

    assert mock_get.call_count == expected_calls
    assert len(result) == expected_rows
    assert any("attempt 1/3 failed" in msg for level, msg in logger.messages if level == "WARNING")
    if expected_rows == 0:
        assert any("Failed to fetch" in msg for _, msg in logger.messages)


@pytest.mark.parametrize(
    "interrupt",
    [
        "trickling-stream",
        pytest.param(
            "blocking-request",
            marks=pytest.mark.skipif(
                not hasattr(signal, "SIGALRM"), reason="SIGALRM is required for the total-attempt deadline"
            ),
        ),
    ],
    ids=["trickling-stream", "blocking-request"],
)
def test_download_attempt_has_a_wall_clock_budget(interrupt, tmp_path, monkeypatch):
    """Both a trickling stream and a pre-first-chunk block are cut off by the attempt deadline."""
    downloader = IBTrACSDownloader(logger=MockLogger(), download_timeout=1)

    if interrupt == "trickling-stream":
        # started = 0.0, then the first chunk check sees 2.0 > 1 -> the attempt is over budget
        ticks = iter([0.0, 2.0])
        monkeypatch.setattr("downloader.ibtracs.time.monotonic", lambda: next(ticks))

        with (
            patch.object(downloader.session, "get", return_value=_mock_csv_response()),
            pytest.raises(requests.exceptions.Timeout, match="download budget"),
        ):
            downloader._download_to("https://example.com/api", str(tmp_path / "ibtracs.csv"))
    else:
        monkeypatch.setattr(downloader, "_download_to", lambda *_args: time.sleep(2))

        with pytest.raises(requests.exceptions.Timeout, match="download budget"):
            downloader._download_attempt("https://example.com/api", str(tmp_path / "ibtracs.csv"))


@pytest.mark.parametrize(
    ("geocode_distance_km", "expected_at_100_km"),
    [(100, "MT"), (50, "")],
    ids=["includes-100km", "excludes-100km"],
)
def test_download_stamps_geocode_pair_with_near_land_filter(tmp_path, geocode_distance_km, expected_at_100_km):
    """Near-land rows are geocoded; far rows get the cached answer or an empty stamp."""
    from reverse_geocode import coord_key, save_cache

    lookup = tmp_path / "reverse_geocode.csv"
    save_cache({coord_key(15.0, 135.0): ("PH", "PSA")}, str(lookup))
    downloader = IBTrACSDownloader(
        logger=MockLogger(), reverse_geocode_file=str(lookup), geocode_distance_km=geocode_distance_km
    )

    with patch.object(downloader.session, "get", return_value=_mock_csv_response()):
        result = downloader.download_by_date_range(
            "https://example.com/api", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 4)
        )

    by_key = {(record["LAT"], record["LON"]): record for record in result}
    assert by_key[("26.0", "-81.0")]["geocode_state"] == expected_at_100_km  # DIST2LAND 100
    assert by_key[("27.0", "-82.0")]["geocode_country"] == "US"  # DIST2LAND 50 → fetched
    assert by_key[("15.0", "135.0")]["geocode_state"] == "PSA"  # far, but cached
    assert by_key[("25.0", "-80.0")]["geocode_country"] == ""  # DIST2LAND 150, not cached
