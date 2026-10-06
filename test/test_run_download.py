import datetime as dt
import sys

import pytest

import run_download
from model import AppConfig, LoadParams, SourceConfig
from model.e_load_type import ELoadType
from run_download import download_source, save_csv
from test.downloader.conftest import MockLogger


class StubDownloader:
    """Fake downloader — returns a scripted result per day, records the calls."""

    def __init__(self, results: dict[str, list[dict]] | None = None) -> None:
        """Map YYYY-MM-DD (or default) to the records the download should return."""
        self.results = results or {}
        self.calls: list[tuple[str, dt.datetime, dt.datetime]] = []
        self.auxiliary_calls: list[str] = []

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Record the call and return the scripted records for that day."""
        self.calls.append((base_url, start_date, end_date))
        return self.results.get(start_date.strftime("%Y-%m-%d"), [])

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Record the hook call — the real downloaders build their ETL references here."""
        self.auxiliary_calls.append(api_url)


class FailingAuxiliaryDownloader(StubDownloader):
    """Stub whose reference files cannot be created."""

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Fail the way a full disk or an unreachable API would."""
        raise OSError("no space left on device")


def _source(output_folder: str) -> SourceConfig:
    """SourceConfig for IBTrACS writing into the given folder."""
    return SourceConfig(
        type="ibtracs",
        enabled=True,
        api_url="https://example.test/csv",
        start_date="2026-09-25",
        output_folder=output_folder,
        output_file_pattern="ibtracs_cyclones_{date}.csv",
    )


def _load_params(output_folder: str) -> LoadParams:
    """A three-day load range ending yesterday."""
    yesterday = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
    return LoadParams(load_type=ELoadType.INCREMENTAL, date_from=yesterday - dt.timedelta(days=2), date_to=yesterday)


def test_save_csv_writes_file_and_returns_true(tmp_path) -> None:
    """save_csv() writes the CSV and reports the file as saved."""
    # Arrange
    rows = [{"ISO_TIME": "2026-09-25 06:00:00", "NAME": "Test"}]
    logger = MockLogger()

    # Act
    saved = save_csv(rows, str(tmp_path), "ibtracs_cyclones_{date}.csv", dt.datetime(2026, 9, 25), logger=logger)

    # Assert
    assert saved is True
    content = (tmp_path / "ibtracs_cyclones_2026-09-25.csv").read_text()
    assert content.splitlines() == ["ISO_TIME,NAME", "2026-09-25 06:00:00,Test"]
    assert any(level == "INFO" and "saved. Records: 1." in msg for level, msg in logger.messages)


def test_save_csv_without_data_returns_false(tmp_path) -> None:
    """save_csv() writes no file and warns when the day has no records."""
    # Arrange
    logger = MockLogger()

    # Act
    saved = save_csv([], str(tmp_path), "ibtracs_cyclones_{date}.csv", dt.datetime(2026, 9, 25), logger=logger)

    # Assert
    assert saved is False
    assert list(tmp_path.iterdir()) == []
    assert ("WARNING", "No data to save for 2026-09-25.") in logger.messages


def test_save_csv_write_error_returns_false(tmp_path) -> None:
    """save_csv() reports a failed write as not saved instead of raising."""
    # Arrange
    missing_folder = tmp_path / "does_not_exist"
    logger = MockLogger()
    rows = [{"ISO_TIME": "2026-09-25 06:00:00"}]

    # Act
    saved = save_csv(rows, str(missing_folder), "ibtracs_cyclones_{date}.csv", dt.datetime(2026, 9, 25), logger=logger)

    # Assert
    assert saved is False
    assert any(level == "ERROR" and "Error saving CSV" in msg for level, msg in logger.messages)


def test_download_source_completes_when_files_written(tmp_path) -> None:
    """With at least one file written the run finishes normally and logs Done."""
    # Arrange
    source = _source(str(tmp_path))
    load_params = _load_params(str(tmp_path))
    day = load_params.date_from.strftime("%Y-%m-%d")
    downloader = StubDownloader({day: [{"ISO_TIME": f"{day} 06:00:00"}]})
    logger = MockLogger()

    # Act
    result = download_source(source, "IBTrACS", load_params, downloader, logger)

    # Assert
    assert result is None
    assert (tmp_path / f"ibtracs_cyclones_{day}.csv").exists()
    assert ("INFO", "Done.") in logger.messages


def test_download_source_raises_when_nothing_downloaded(tmp_path) -> None:
    """A run that writes no files raises RuntimeError, so the process exits non-zero."""
    # Arrange
    source = _source(str(tmp_path))
    load_params = _load_params(str(tmp_path))
    downloader = StubDownloader()
    logger = MockLogger()

    # Act & Assert
    with pytest.raises(RuntimeError, match="No files downloaded for IBTrACS"):
        download_source(source, "IBTrACS", load_params, downloader, logger)

    assert list(tmp_path.iterdir()) == []
    assert len(downloader.calls) == 3
    assert ("WARNING", f"No data to save for {load_params.date_from.strftime('%Y-%m-%d')}.") in logger.messages
    assert any(level == "ERROR" and "No files downloaded for IBTrACS" in msg for level, msg in logger.messages)
    assert ("INFO", "Done.") not in logger.messages


def test_download_source_builds_auxiliary_files_after_the_run(tmp_path) -> None:
    """With files written the downloader gets to create the references the ETL joins."""
    # Arrange
    source = _source(str(tmp_path))
    load_params = _load_params(str(tmp_path))
    day = load_params.date_from.strftime("%Y-%m-%d")
    downloader = StubDownloader({day: [{"ISO_TIME": f"{day} 06:00:00"}]})
    logger = MockLogger()

    # Act
    download_source(source, "IBTrACS", load_params, downloader, logger)

    # Assert
    assert downloader.auxiliary_calls == ["https://example.test/csv"]
    assert ("INFO", "Done.") in logger.messages


def test_download_source_skips_auxiliary_files_when_nothing_downloaded(tmp_path) -> None:
    """A run that wrote no CSV never reaches the reference files."""
    # Arrange
    source = _source(str(tmp_path))
    load_params = _load_params(str(tmp_path))
    downloader = StubDownloader()
    logger = MockLogger()

    # Act & Assert
    with pytest.raises(RuntimeError, match="No files downloaded for IBTrACS"):
        download_source(source, "IBTrACS", load_params, downloader, logger)

    assert downloader.auxiliary_calls == []


def test_download_source_keeps_going_when_auxiliary_files_fail(tmp_path) -> None:
    """The day CSVs are written already, so a failing reference is logged, not raised."""
    # Arrange
    source = _source(str(tmp_path))
    load_params = _load_params(str(tmp_path))
    day = load_params.date_from.strftime("%Y-%m-%d")
    downloader = FailingAuxiliaryDownloader({day: [{"ISO_TIME": f"{day} 06:00:00"}]})
    logger = MockLogger()

    # Act
    result = download_source(source, "IBTrACS", load_params, downloader, logger)

    # Assert
    assert result is None
    assert (tmp_path / f"ibtracs_cyclones_{day}.csv").exists()
    assert any(level == "ERROR" and "Auxiliary files of IBTrACS" in msg for level, msg in logger.messages)
    assert ("INFO", "Done.") in logger.messages


def test_main_returns_zero_when_nothing_to_download(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the local data is already current, main() exits 0 without downloading."""
    # Arrange — a file dated today means date_from (tomorrow) > date_to (yesterday)
    source = _source(str(tmp_path))
    (tmp_path / f"ibtracs_cyclones_{dt.datetime.now():%Y-%m-%d}.csv").touch()
    config = AppConfig(sources={"IBTrACS": source})
    logger = MockLogger()

    monkeypatch.setattr(run_download.AppConfig, "from_json", staticmethod(lambda: config))
    monkeypatch.setattr(run_download.util, "setup_logger", lambda **kwargs: logger)
    monkeypatch.setattr(sys, "argv", ["run_download.py", "IBTrACS"])

    def _fail_get_downloader(*args, **kwargs):
        raise AssertionError("get_downloader must not be called when there is nothing to download")

    monkeypatch.setattr(run_download, "get_downloader", _fail_get_downloader)

    # Act
    exit_code = run_download.main()

    # Assert
    assert exit_code == 0
    assert any("Nothing to download" in msg for _, msg in logger.messages)
    assert ("INFO", "Done.") in logger.messages


def test_main_raises_when_nothing_downloaded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() propagates the no-files failure as RuntimeError (exit code 1 when uncaught)."""
    # Arrange — empty folder → HISTORICAL from start_date 2026-09-25 to yesterday
    source = _source(str(tmp_path))
    config = AppConfig(sources={"IBTrACS": source})
    logger = MockLogger()

    monkeypatch.setattr(run_download.AppConfig, "from_json", staticmethod(lambda: config))
    monkeypatch.setattr(run_download.util, "setup_logger", lambda **kwargs: logger)
    monkeypatch.setattr(run_download, "get_downloader", lambda *args, **kwargs: StubDownloader())
    monkeypatch.setattr(sys, "argv", ["run_download.py", "IBTrACS"])

    # Act & Assert
    with pytest.raises(RuntimeError, match="No files downloaded for IBTrACS"):
        run_download.main()

    assert any(level == "ERROR" and "No files downloaded for IBTrACS" in msg for level, msg in logger.messages)
