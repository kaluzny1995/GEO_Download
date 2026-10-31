import datetime as dt
import json

import pytest

from model import AppConfig, ELoadType, LoadParams, SourceConfig


def _source_config(**overrides) -> SourceConfig:
    """Build the standard test SourceConfig (all 7 required kwargs) with per-test overrides."""
    kwargs = {
        "type": "usgs_earthquake",
        "enabled": True,
        "api_url": "https://example.com/api",
        "feed_url": "https://example.com/feed",
        "start_date": "2026-09-01",
        "output_folder": "data/test",
        "output_file_pattern": "test_{date}.csv",
    }
    kwargs.update(overrides)
    return SourceConfig(**kwargs)


@pytest.mark.parametrize(
    ("overrides", "expected_previous_day"),
    [
        ({}, True),
        ({"is_date_to_previous_day": False}, False),
    ],
)
def test_source_config_creation_and_date_flag(overrides, expected_previous_day):
    # Arrange & Act
    source = _source_config(**overrides)

    # Assert
    assert source.type == "usgs_earthquake"
    assert source.enabled is True
    assert source.api_url == "https://example.com/api"
    assert source.is_date_to_previous_day is expected_previous_day


def test_app_config_from_json(tmp_path):
    # Arrange
    config_file = tmp_path / "config.json"
    config_file.write_text("""
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
    """)

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
                output_file_pattern="source1_{date}.csv",
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


@pytest.mark.parametrize(
    ("overrides", "expected_yesterday"),
    [
        ({}, True),
        ({"is_date_to_previous_day": True}, True),
        ({"is_date_to_previous_day": False}, False),
    ],
)
def test_load_params_from_source_historical_and_date_to(tmp_path, overrides, expected_yesterday):
    # Arrange
    source = _source_config(output_folder=str(tmp_path / "empty_data"), **overrides)

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    start_of_today = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    expected_date_to = start_of_today - (dt.timedelta(days=1) if expected_yesterday else dt.timedelta(0))
    assert load_params.load_type == ELoadType.HISTORICAL
    assert load_params.date_from == dt.datetime(2026, 9, 1)
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
        output_file_pattern="test_{date}.csv",
    )

    # Act
    load_params = LoadParams.from_source(source)

    # Assert
    assert load_params.load_type == ELoadType.INCREMENTAL
    assert load_params.date_from == dt.datetime(2026, 9, 6)
