from unittest.mock import patch, MagicMock
import datetime as dt

from downloader.avalanche_org import AvalancheOrgDownloader


def _make_feature(danger_level=2, danger="moderate", zone_name="Front Range", center_id="CAIC", state="CO"):
    return {
        "type": "Feature",
        "id": 2688,
        "properties": {
            "name": zone_name,
            "center": "Colorado Avalanche Information Center",
            "center_link": "https://avalanche.state.co.us/",
            "timezone": "America/Denver",
            "center_id": center_id,
            "state": state,
            "off_season": False,
            "travel_advice": "Watch for signs of unstable snow.",
            "danger": danger,
            "danger_level": danger_level,
            "color": "#FFFF00",
            "stroke": "#484848",
            "font_color": "#000000",
            "link": "https://avalanche.state.co.us/",
            "start_date": "2026-09-16T14:00:00",
            "end_date": "2026-09-17T14:00:00",
            "fillOpacity": 0.5,
            "fillIncrement": 0.1,
            "warning": {"product": None},
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-105.5, 39.5], [-105.3, 39.5], [-105.3, 39.7], [-105.5, 39.7], [-105.5, 39.5]]],
        },
    }


def test_build_record():
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature()
    record = dl._build_record(feature)
    assert record["zone_name"] == "Front Range"
    assert record["center_id"] == "CAIC"
    assert record["danger_level"] == 2
    assert record["danger_rating"] == "moderate"
    assert record["off_season"] is False


def test_build_record_no_warning():
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature()
    feature["properties"]["warning"] = {"product": None}
    record = dl._build_record(feature)
    assert record["warning"] == ""


def test_build_record_with_warning():
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature()
    feature["properties"]["warning"] = {"product": "Avalanche Warning in effect"}
    record = dl._build_record(feature)
    assert record["warning"] == "Avalanche Warning in effect"


def test_build_record_empty_properties():
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = {"type": "Feature", "id": 1, "properties": {}, "geometry": None}
    record = dl._build_record(feature)
    assert record["zone_name"] == ""
    assert record["danger_level"] == ""
    assert record["warning"] == ""


@patch("downloader.base.BaseDownloader._get_json")
def test_download(mock_get_json):
    mock_get_json.return_value = {
        "type": "FeatureCollection",
        "features": [_make_feature()],
    }
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()
    start = dt.datetime(2026, 9, 15)
    end = dt.datetime(2026, 9, 15)
    records = dl.download_by_date_range("unused", start, end)
    assert len(records) == 1
    assert records[0]["zone_name"] == "Front Range"
    assert records[0]["date"] == "2026-09-15"


@patch("downloader.base.BaseDownloader._get_json")
def test_download_empty(mock_get_json):
    mock_get_json.return_value = {"type": "FeatureCollection", "features": []}
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()
    start = dt.datetime(2026, 9, 15)
    end = dt.datetime(2026, 9, 15)
    records = dl.download_by_date_range("unused", start, end)
    assert records == []


@patch("downloader.base.BaseDownloader._get_json")
def test_download_no_data(mock_get_json):
    mock_get_json.return_value = None
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()
    start = dt.datetime(2026, 9, 15)
    end = dt.datetime(2026, 9, 15)
    records = dl.download_by_date_range("unused", start, end)
    assert records == []


@patch("downloader.base.BaseDownloader._get_json")
def test_download_multiple_days(mock_get_json):
    feature1 = _make_feature(danger_level=2, danger="moderate")
    feature2 = _make_feature(danger_level=3, danger="considerable", zone_name=" Mosquito Range")
    mock_get_json.side_effect = [
        {"type": "FeatureCollection", "features": [feature1]},
        {"type": "FeatureCollection", "features": [feature2]},
    ]
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()
    start = dt.datetime(2026, 9, 14)
    end = dt.datetime(2026, 9, 15)
    records = dl.download_by_date_range("unused", start, end)
    assert len(records) == 2
    assert records[0]["date"] == "2026-09-14"
    assert records[1]["date"] == "2026-09-15"
