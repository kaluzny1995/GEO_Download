import json
import pytest
import datetime as dt

from model import AppConfig, SourceConfig, LoadParams, ELoadType


def test_source_config_creation():
    # Arrange
    # Act
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder="data/test",
        output_file_pattern="test_{date}.csv"
    )

    # Assert
    assert source.type == "usgs_earthquake"
    assert source.enabled is True
    assert source.api_url == "https://example.com/api"


def test_source_config_is_date_to_previous_day_default():
    # Arrange
    # Act
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder="data/test",
        output_file_pattern="test_{date}.csv"
    )

    # Assert
    assert source.is_date_to_previous_day is True


def test_source_config_is_date_to_previous_day_false():
    # Arrange
    # Act
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder="data/test",
        output_file_pattern="test_{date}.csv",
        is_date_to_previous_day=False
    )

    # Assert
    assert source.is_date_to_previous_day is False


def test_app_config_from_json(tmp_path):
    # Arrange
    config_file = tmp_path / "config.json"
    config_file.write_text('''
    {
        "sources": {
            "TestSource": {
                "type": "test_type",
                "enabled": true,
                "api_url": "https://example.com/api",
                "feed_url": "https://example.com/feed",
                "start_date": "2026-09-01",
                "output_folder": "data/test",
                "output_file_pattern": "test_{date}.csv"
            }
        }
    }
    ''')

    # Act
    with open(config_file) as f:
        config = AppConfig(**json.load(f))

    # Assert
    assert "TestSource" in config.sources
    assert config.sources["TestSource"].type == "test_type"


def test_app_config_get_source_by_name():
    # Arrange
    config = AppConfig(
        sources={
            "Source1": SourceConfig(
                type="type1",
                enabled=True,
                api_url="https://example.com/api1",
                feed_url="https://example.com/feed1",
                start_date="2026-09-01",
                output_folder="data/source1",
                output_file_pattern="source1_{date}.csv"
            )
        }
    )

    # Act
    source = config.get_source_by_name("Source1")

    # Assert
    assert source.type == "type1"


def test_app_config_get_source_by_name_not_found():
    # Arrange
    config = AppConfig(sources={})

    # Act & Assert
    with pytest.raises(ValueError, match="not found"):
        config.get_source_by_name("Nonexistent")


def test_load_params_from_source_historical(tmp_path):
    # Arrange
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder=str(tmp_path / "empty_data"),
        output_file_pattern="test_{date}.csv"
    )

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    assert load_params.load_type == ELoadType.HISTORICAL
    assert load_params.date_from == dt.datetime(2026, 9, 1)


def test_load_params_date_to_previous_day_true(tmp_path):
    # Arrange
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder=str(tmp_path / "empty_data"),
        output_file_pattern="test_{date}.csv",
        is_date_to_previous_day=True
    )

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    expected_date_to = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
    assert load_params.date_to == expected_date_to


def test_load_params_date_to_previous_day_false(tmp_path):
    # Arrange
    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder=str(tmp_path / "empty_data"),
        output_file_pattern="test_{date}.csv",
        is_date_to_previous_day=False
    )

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    expected_date_to = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    assert load_params.date_to == expected_date_to


def test_load_params_from_source_incremental(tmp_path):
    # Arrange
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "test_2026-09-05.csv").touch()

    source = SourceConfig(
        type="usgs_earthquake",
        enabled=True,
        api_url="https://example.com/api",
        feed_url="https://example.com/feed",
        start_date="2026-09-01",
        output_folder=str(folder),
        output_file_pattern="test_{date}.csv"
    )

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    assert load_params.load_type == ELoadType.INCREMENTAL
    assert load_params.date_from == dt.datetime(2026, 9, 5)
