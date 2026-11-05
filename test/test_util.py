import datetime as dt
import logging
import os
import sys

import pytest

import util


@pytest.mark.parametrize(
    "start_date, end_date, expected_dates",
    [
        (
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 3),
            [dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2), dt.datetime(2026, 9, 3)],
        ),
        (dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 1), [dt.datetime(2026, 9, 1)]),
        (
            dt.datetime(2026, 12, 30),
            dt.datetime(2027, 1, 2),
            [dt.datetime(2026, 12, 30), dt.datetime(2026, 12, 31), dt.datetime(2027, 1, 1), dt.datetime(2027, 1, 2)],
        ),
    ],
)
def test_date_range(start_date: dt.datetime, end_date: dt.datetime, expected_dates: list[dt.datetime]) -> None:
    # Arrange
    # Act
    dates = list(util.date_range(start_date, end_date))

    # Assert
    assert len(dates) == len(expected_dates)
    for date, expected_date in zip(dates, expected_dates, strict=True):
        assert date == expected_date


def test_get_recent_file_date_with_files(tmp_path):
    # Arrange
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "earthquakes_2026-09-01.csv").touch()
    (folder / "earthquakes_2026-09-05.csv").touch()
    (folder / "earthquakes_2026-09-03.csv").touch()

    # Act
    result = util.get_recent_file_date(str(folder))

    # Assert
    assert result == dt.datetime(2026, 9, 5)


def test_get_recent_file_date_empty_folder(tmp_path):
    # Arrange
    folder = tmp_path / "data"
    folder.mkdir()

    # Act
    result = util.get_recent_file_date(str(folder))

    # Assert
    assert result is None


def test_get_recent_file_date_nonexistent_folder():
    # Arrange
    # Act
    result = util.get_recent_file_date("/nonexistent/path")

    # Assert
    assert result is None


def test_get_recent_file_date_no_csv_files(tmp_path):
    # Arrange
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "readme.txt").touch()

    # Act
    result = util.get_recent_file_date(str(folder))

    # Assert
    assert result is None


def test_setup_logger_writes_file_and_mirrors_stdout(tmp_path):
    # Arrange
    log_file = str(tmp_path / "test.log")

    # Act
    logger = util.setup_logger(name="test_setup_logger", log_file=log_file)
    logger.info("hello world")

    # Assert — file content
    with open(log_file) as f:
        content = f.read()
    assert "INFO" in content
    assert "hello world" in content
    # Assert — one FileHandler + one plain stdout StreamHandler
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    stream_handlers = [
        h for h in logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert len(file_handlers) == 1
    assert len(stream_handlers) == 1
    assert stream_handlers[0].stream is sys.stdout


def test_setup_logger_no_duplicate_handlers(tmp_path):
    # Arrange
    log_file = str(tmp_path / "test.log")

    # Act
    logger1 = util.setup_logger(name="test_setup_logger_dedup", log_file=log_file)
    logger2 = util.setup_logger(name="test_setup_logger_dedup", log_file=log_file)

    # Assert
    assert logger1 is logger2
    file_handlers = [h for h in logger1.handlers if isinstance(h, logging.FileHandler)]
    stream_handlers = [
        h for h in logger1.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert len(file_handlers) == 1
    assert len(stream_handlers) == 1


def test_setup_logger_survives_concurrent_directory_creation(tmp_path, monkeypatch):
    """A concurrent task creating the log folder must not crash the logger.

    Simulate the TOCTOU window: the folder exists but the logger's existence check
    still reports it missing, as if another task had just created it between the
    check and ``makedirs`` (the Airflow download pool runs several sources at once).
    """
    # Arrange
    log_folder = tmp_path / "logs" / "USGS_Earthquake"
    log_folder.mkdir(parents=True)
    real_exists = os.path.exists

    def racing_exists(path):
        if os.path.abspath(path) == os.path.abspath(log_folder):
            return False
        return real_exists(path)

    monkeypatch.setattr("util.os.path.exists", racing_exists)
    log_file = str(log_folder / "download.log")

    # Act
    logger = util.setup_logger(name="test_setup_logger_race", log_file=log_file)
    logger.info("survived the race")

    # Assert
    assert os.path.exists(log_file)
    with open(log_file) as f:
        assert "survived the race" in f.read()
