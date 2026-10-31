import datetime as dt
from unittest.mock import patch

import pytest

from downloader.base import BaseDownloader
from downloader.gdacs import GDACSDownloader
from test.downloader.conftest import MockLogger, create_downloader

SAMPLE_FEATURES = [
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-66.4888, -25.4555]},
        "properties": {
            "eventtype": "EQ",
            "eventid": 1566388,
            "name": "Earthquake in Argentina",
            "alertlevel": "Green",
            "country": "Argentina",
            "iso3": "ARG",
            "fromdate": "2026-09-15T17:41:25",
            "todate": "2026-09-15T17:41:25",
            "datemodified": "2026-09-15T19:03:46",
            "source": "NEIC",
            "iscurrent": True,
            "severitydata": {"severity": 4.5, "severitytext": "Magnitude 4.5M, Depth:185.605km", "severityunit": "M"},
            "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1566388"},
        },
    },
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [14.946, -5.4744]},
        "properties": {
            "eventtype": "WF",
            "eventid": 1031804,
            "name": "Forest fires in The Democratic Republic of Congo",
            "alertlevel": "Green",
            "country": "The Democratic Republic of Congo",
            "iso3": "COD",
            "fromdate": "2026-08-31T00:00:00",
            "todate": "2026-09-15T00:00:00",
            "datemodified": "2026-09-15T15:31:35",
            "source": "GWIS",
            "iscurrent": True,
            "severitydata": {
                "severity": 6223.0,
                "severitytext": "Green impact for forestfire in 6223 ha",
                "severityunit": "ha",
            },
            "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1031804"},
        },
    },
]


def test_build_record():
    downloader = create_downloader(GDACSDownloader)

    record = downloader._build_record(SAMPLE_FEATURES[0])

    assert record["event_type"] == "EQ"
    assert record["event_id"] == 1566388
    assert record["event_name"] == "Earthquake in Argentina"
    assert record["alert_level"] == "Green"
    assert record["country"] == "Argentina"
    assert record["country_code"] == "ARG"
    assert record["latitude"] == -25.4555
    assert record["longitude"] == -66.4888
    assert record["from_date"] == "2026-09-15T17:41:25"
    assert record["severity"] == 4.5
    assert record["severity_text"] == "Magnitude 4.5M, Depth:185.605km"
    assert record["source"] == "NEIC"
    assert "report.aspx" in record["report_url"]


def test_build_record_missing_geometry():
    downloader = create_downloader(GDACSDownloader)
    feature = {"type": "Feature", "geometry": None, "properties": {"eventtype": "EQ", "eventid": 1}}

    record = downloader._build_record(feature)

    assert record["latitude"] is None
    assert record["longitude"] is None


def test_download_by_date_range():
    logger = MockLogger()
    downloader = create_downloader(GDACSDownloader, logger)

    def mock_get_json(_url):
        return {"type": "FeatureCollection", "features": SAMPLE_FEATURES}

    with patch.object(BaseDownloader, "_get_json", side_effect=mock_get_json):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 14),
            dt.datetime(2026, 9, 15),
        )

    assert len(result) == 2
    assert result[0]["event_type"] == "EQ"
    assert result[0]["country"] == "Argentina"
    assert result[1]["event_type"] == "WF"
    assert result[1]["country_code"] == "COD"


def test_download_by_date_range_pagination():
    logger = MockLogger()
    downloader = create_downloader(GDACSDownloader, logger)

    page1_features = SAMPLE_FEATURES * 50
    page2_features = SAMPLE_FEATURES[:1]

    call_count = 0

    def mock_get_json(_url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"type": "FeatureCollection", "features": page1_features}
        return {"type": "FeatureCollection", "features": page2_features}

    with patch.object(BaseDownloader, "_get_json", side_effect=mock_get_json):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 14),
            dt.datetime(2026, 9, 15),
        )

    assert len(result) == 101
    assert call_count == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "FeatureCollection", "features": []},
        None,
    ],
)
def test_download_by_date_range_empty_or_no_data(payload):
    logger = MockLogger()
    downloader = create_downloader(GDACSDownloader, logger)

    with patch.object(BaseDownloader, "_get_json", return_value=payload):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 1),
            dt.datetime(2026, 9, 2),
        )

    assert result == []


def test_download_stamps_geocode_country_and_state(tmp_path):
    """Every event centroid is reverse-geocoded; the source country_code is untouched."""
    lookup = str(tmp_path / "reverse_geocode.csv")
    downloader = GDACSDownloader(logger=MockLogger(), reverse_geocode_file=lookup)

    def mock_get_json(_url):
        return {"type": "FeatureCollection", "features": SAMPLE_FEATURES}

    with patch.object(BaseDownloader, "_get_json", side_effect=mock_get_json):
        result = downloader.download_by_date_range(
            "https://ignored.com",
            dt.datetime(2026, 9, 14),
            dt.datetime(2026, 9, 15),
        )

    assert len(result) == 2
    assert all(record["geocode_country"] == "US" for record in result)
    assert all(record["geocode_state"] == "MT" for record in result)
    assert result[1]["country_code"] == "COD"
