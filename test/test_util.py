import datetime as dt

import pytest

import util


@pytest.mark.parametrize("start_date, end_date, expected_dates", [
    (dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 3), [
        dt.datetime(2026, 9, 1),
        dt.datetime(2026, 9, 2),
        dt.datetime(2026, 9, 3)
    ]),
    (dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 1), [
        dt.datetime(2026, 9, 1)
    ]),
    (dt.datetime(2026, 12, 30), dt.datetime(2027, 1, 2), [
        dt.datetime(2026, 12, 30),
        dt.datetime(2026, 12, 31),
        dt.datetime(2027, 1, 1),
        dt.datetime(2027, 1, 2)
    ]),
])
def test_date_range(start_date: dt.datetime, end_date: dt.datetime,
                    expected_dates: list[dt.datetime]) -> None:
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
