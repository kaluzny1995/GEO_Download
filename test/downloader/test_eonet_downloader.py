import datetime as dt
from unittest.mock import patch

from downloader.base import BaseDownloader
from downloader.eonet import EONETDownloader
from test.downloader.conftest import MockLogger

SAMPLE_EVENTS = [
    {
        "id": "EONET_24184",
        "title": "Cyclone Norbert",
        "description": "Tropical cyclone in the Pacific",
        "closed": None,
        "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
        "sources": [{"id": "JTWC", "url": "https://example.com/jtwc"}],
        "geometry": [
            {
                "magnitudeValue": 35.0,
                "magnitudeUnit": "kts",
                "date": "2026-09-10T06:00:00Z",
                "type": "Point",
                "coordinates": [-117.3, 16.4],
            },
            {
                "magnitudeValue": 55.0,
                "magnitudeUnit": "kts",
                "date": "2026-09-11T12:00:00Z",
                "type": "Point",
                "coordinates": [-124.1, 16.6],
            },
        ],
    },
    {
        "id": "EONET_24180",
        "title": "Wildfire in California",
        "description": None,
        "closed": "2026-09-12T00:00:00Z",
        "categories": [{"id": "wildfires", "title": "Wildfires"}],
        "sources": [{"id": "IRWIN", "url": "https://example.com/irwin"}],
        "geometry": [
            {
                "magnitudeValue": 914.0,
                "magnitudeUnit": "acres",
                "date": "2026-09-08T16:57:00Z",
                "type": "Point",
                "coordinates": [-98.678, 34.841],
            },
        ],
    },
    {
        "id": "EONET_24190",
        "title": "Flood in Bangladesh",
        "description": "Monsoon flooding",
        "closed": None,
        "categories": [{"id": "floods", "title": "Floods"}],
        "sources": [{"id": "GDACS", "url": "https://example.com/gdacs"}],
        "geometry": [
            {
                "magnitudeValue": None,
                "magnitudeUnit": None,
                "date": "2026-09-11T20:00:00Z",
                "type": "Polygon",
                "coordinates": [[[22.53, 92.62], [22.52, 92.62]]],
            },
        ],
    },
]


def _create_downloader(logger=None):
    if logger is None:
        logger = MockLogger()
    return EONETDownloader(logger=logger)


def test_build_record():
    downloader = _create_downloader()

    record = downloader._build_record(SAMPLE_EVENTS[0])

    assert record["event_id"] == "EONET_24184"
    assert record["event_name"] == "Cyclone Norbert"
    assert record["category_id"] == "severeStorms"
    assert record["category_name"] == "Severe Storms"
    assert record["description"] == "Tropical cyclone in the Pacific"
    assert record["source_id"] == "JTWC"
    assert record["latitude"] == 16.4
    assert record["longitude"] == -117.3
    assert record["event_date"] == "2026-09-10T06:00:00Z"
    assert record["magnitude_value"] == 35.0
    assert record["magnitude_unit"] == "kts"
    assert record["closed"] == ""
    assert record["geometry_count"] == 2
    assert record["last_latitude"] == 16.6
    assert record["last_longitude"] == -124.1
    assert record["last_date"] == "2026-09-11T12:00:00Z"


def test_build_record_closed_event():
    downloader = _create_downloader()

    record = downloader._build_record(SAMPLE_EVENTS[1])

    assert record["event_id"] == "EONET_24180"
    assert record["event_name"] == "Wildfire in California"
    assert record["category_id"] == "wildfires"
    assert record["description"] == ""
    assert record["closed"] == "2026-09-12T00:00:00Z"
    assert record["geometry_count"] == 1


def test_build_record_polygon_geometry():
    downloader = _create_downloader()

    record = downloader._build_record(SAMPLE_EVENTS[2])

    assert record["event_id"] == "EONET_24190"
    assert record["category_id"] == "floods"
    assert record["latitude"] == 92.62
    assert record["longitude"] == 22.53
    assert record["magnitude_value"] == ""
    assert record["magnitude_unit"] == ""


def test_download_by_date_range():
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(BaseDownloader, "_get_json", return_value={"events": SAMPLE_EVENTS}):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 10),
            dt.datetime(2026, 9, 11),
        )

    assert len(result) == 3
    assert result[0]["event_id"] == "EONET_24184"
    assert result[0]["category_name"] == "Severe Storms"
    assert result[1]["category_name"] == "Wildfires"
    assert result[2]["category_name"] == "Floods"


def test_download_by_date_range_empty():
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(BaseDownloader, "_get_json", return_value={"events": []}):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    assert result == []


def test_download_by_date_range_no_data():
    logger = MockLogger()
    downloader = _create_downloader(logger)

    with patch.object(BaseDownloader, "_get_json", return_value=None):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    assert result == []


def test_build_record_missing_geometry():
    downloader = _create_downloader()
    event = {
        "id": "EONET_99999",
        "title": "No Geometry Event",
        "description": None,
        "closed": None,
        "categories": [],
        "sources": [],
        "geometry": [],
    }

    record = downloader._build_record(event)

    assert record["event_id"] == "EONET_99999"
    assert record["latitude"] == ""
    assert record["longitude"] == ""
    assert record["geometry_count"] == 0
    assert record["category_id"] == ""
    assert record["source_id"] == ""
