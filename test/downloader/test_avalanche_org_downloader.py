import csv
import datetime as dt
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from downloader.avalanche_org import AvalancheOrgDownloader


def _make_feature(danger_level=2, danger="moderate", zone_name="Front Range", center_id="CAIC",
                  state="CO") -> dict[str, Any]:
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
    assert record["latitude"] == pytest.approx(39.6)
    assert record["longitude"] == pytest.approx(-105.4)


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
    assert record["latitude"] == ""
    assert record["longitude"] == ""


def test_build_record_without_geometry_has_empty_centroid():
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature()
    feature["geometry"] = None
    record = dl._build_record(feature)
    assert record["latitude"] == ""
    assert record["longitude"] == ""


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
    feature2 = _make_feature(danger_level=3, danger="considerable", zone_name="Mosquito Range")
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


def test_default_notices_file_points_next_to_rivers_json():
    dl = AvalancheOrgDownloader(logger=MagicMock())
    assert dl.notices_file == AvalancheOrgDownloader.DEFAULT_NOTICES_FILE
    assert dl.notices_file.endswith(os.path.join("data", "avalanche_org_notices.csv"))


class TestNoticesLookup:
    @staticmethod
    def _downloader(tmp_path) -> AvalancheOrgDownloader:
        dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
        dl.logger = MagicMock()
        dl.notices_file = str(tmp_path / "avalanche_org_notices.csv")
        return dl

    @staticmethod
    def _rows(path: str) -> list[dict[str, str]]:
        with open(path, newline="") as handle:
            return list(csv.DictReader(handle))

    @patch("downloader.base.BaseDownloader._get_json")
    def test_download_writes_the_lookup(self, mock_get_json, tmp_path):
        mock_get_json.return_value = {"type": "FeatureCollection", "features": [_make_feature()]}
        dl = self._downloader(tmp_path)
        records = dl.download_by_date_range("unused", dt.datetime(2026, 9, 15), dt.datetime(2026, 9, 15))

        assert len(records) == 1
        rows = self._rows(dl.notices_file)
        assert len(rows) == 1
        assert rows[0]["place_location"] == "Front Range"
        assert rows[0]["state"] == "CO"
        assert float(rows[0]["latitude"]) == pytest.approx(39.6)
        assert float(rows[0]["longitude"]) == pytest.approx(-105.4)

    @patch("downloader.base.BaseDownloader._get_json")
    def test_download_keeps_zones_absent_from_the_feed(self, mock_get_json, tmp_path):
        dl = self._downloader(tmp_path)
        with open(dl.notices_file, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["place_location", "state", "latitude", "longitude"])
            writer.writerow(["Whitefish Range", "MT", 48.8, -114.0])
        mock_get_json.return_value = {"type": "FeatureCollection", "features": [_make_feature()]}

        dl.download_by_date_range("unused", dt.datetime(2026, 9, 15), dt.datetime(2026, 9, 15))

        rows = self._rows(dl.notices_file)
        assert [(row["place_location"], row["state"]) for row in rows] == [
            ("Front Range", "CO"),
            ("Whitefish Range", "MT"),
        ]
        assert rows[1]["latitude"] == "48.8"

    def test_merge_refreshes_coordinates_of_a_known_zone(self, tmp_path):
        dl = self._downloader(tmp_path)
        with open(dl.notices_file, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["place_location", "state", "latitude", "longitude"])
            writer.writerow(["Front Range", "CO", 0.0, 0.0])

        dl._update_notices([{"zone_name": " Front Range ", "state": "CO", "latitude": 39.6, "longitude": -105.4}])

        rows = self._rows(dl.notices_file)
        assert len(rows) == 1
        assert float(rows[0]["latitude"]) == pytest.approx(39.6)
        assert float(rows[0]["longitude"]) == pytest.approx(-105.4)

    def test_records_without_coordinates_do_not_enter_the_lookup(self, tmp_path):
        dl = self._downloader(tmp_path)

        dl._update_notices([{"zone_name": "No Geometry", "state": "CO", "latitude": "", "longitude": ""}])

        assert not os.path.exists(dl.notices_file)

    def test_empty_record_list_writes_nothing(self, tmp_path):
        dl = self._downloader(tmp_path)

        dl._update_notices([])

        assert not os.path.exists(dl.notices_file)
