import csv
import datetime as dt
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from downloader.avalanche_org import AvalancheOrgDownloader

MAP_LAYER_URL = "https://api.avalanche.org/v2/public/products/map-layer"
FORECAST_URL = "https://api.avalanche.org/v2/public/product"


def _make_feature(
    danger_level=2, danger="moderate", zone_name="Front Range", center_id="CAIC", state="CO"
) -> dict[str, Any]:
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


def _make_product(*sizes, published="2026-09-15T14:35:00+00:00", expires="2026-09-17T14:00:00+00:00") -> dict:
    """A forecast product whose problems carry one ``size`` array each."""
    return {
        "published_time": published,
        "expires_time": expires,
        "forecast_avalanche_problems": [{"name": "Wind Slab", "size": list(sizes)}] if sizes else [],
    }


def _map_layer_then(features_by_day: list[list[dict]], product: dict | None = None):
    """Side effect answering map-layer per day and the forecast product otherwise."""

    def _side_effect(url: str):
        if "products/map-layer" in url:
            return {"type": "FeatureCollection", "features": features_by_day.pop(0)}
        return product

    return _side_effect


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
    assert record["avalanche_size"] == ""


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
    assert record["avalanche_size"] == ""


def test_forecast_url_is_the_product_route_beside_the_map_layer():
    assert AvalancheOrgDownloader._forecast_url(MAP_LAYER_URL) == FORECAST_URL


def test_avalanche_size_takes_the_largest_class_across_problems_and_bands():
    product = {
        "forecast_avalanche_problems": [
            {"name": "Wind Slab", "size": ["2", "2.5"]},
            {"name": "Persistent Slab", "size": ["1", "3"]},
        ]
    }

    assert AvalancheOrgDownloader._avalanche_size(product) == "3"


def test_avalanche_size_renders_half_steps_without_trailing_zeros():
    assert AvalancheOrgDownloader._avalanche_size(_make_product("2.5", "1")) == "2.5"


def test_avalanche_size_is_empty_without_problems_or_parseable_values():
    assert AvalancheOrgDownloader._avalanche_size(_make_product()) == ""
    assert AvalancheOrgDownloader._avalanche_size(None) == ""
    assert AvalancheOrgDownloader._avalanche_size({"forecast_avalanche_problems": [{"size": ["", "n/a"]}]}) == ""


def test_product_covers_day_inside_the_publish_expiry_window():
    product = _make_product("2", published="2026-09-15T14:35:00+00:00", expires="2026-09-17T14:00:00+00:00")

    assert AvalancheOrgDownloader._product_covers_day(product, dt.date(2026, 9, 15))
    assert AvalancheOrgDownloader._product_covers_day(product, dt.date(2026, 9, 17))
    assert not AvalancheOrgDownloader._product_covers_day(product, dt.date(2026, 9, 14))
    assert not AvalancheOrgDownloader._product_covers_day(product, dt.date(2026, 9, 18))


def test_product_covers_day_is_false_for_missing_or_unreadable_product():
    assert not AvalancheOrgDownloader._product_covers_day(None, dt.date(2026, 9, 15))
    assert not AvalancheOrgDownloader._product_covers_day({}, dt.date(2026, 9, 15))
    assert not AvalancheOrgDownloader._product_covers_day(
        {"published_time": "not-a-date", "expires_time": "2026-09-17T14:00:00+00:00"}, dt.date(2026, 9, 15)
    )


@patch("downloader.base.BaseDownloader._get_json")
def test_zone_size_skips_unrated_zones(mock_get_json):
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature(danger_level=-1, danger="no rating")

    assert dl._zone_size(feature, FORECAST_URL, dt.date(2026, 9, 15), {}) == ""
    mock_get_json.assert_not_called()


@patch("downloader.base.BaseDownloader._get_json")
def test_zone_size_uses_the_cached_product_only_when_it_covers_the_day(mock_get_json):
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    feature = _make_feature()
    product = _make_product("2", "3", published="2026-09-15T14:35:00+00:00", expires="2026-09-16T14:00:00+00:00")
    mock_get_json.return_value = product
    cache: dict = {}

    assert dl._zone_size(feature, FORECAST_URL, dt.date(2026, 9, 15), cache) == "3"
    assert dl._zone_size(feature, FORECAST_URL, dt.date(2026, 9, 16), cache) == "3"
    assert dl._zone_size(feature, FORECAST_URL, dt.date(2026, 9, 17), cache) == ""
    mock_get_json.assert_called_once()


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
    # The mock answered the forecast call with the FeatureCollection, which
    # is not a product (no publish/expiry window) → no size attached.
    assert records[0]["avalanche_size"] == ""


@patch("downloader.base.BaseDownloader._get_json")
def test_download_attaches_the_size_of_a_covering_product(mock_get_json):
    product = _make_product("2", "3", published="2026-09-15T14:35:00+00:00", expires="2026-09-16T14:00:00+00:00")
    mock_get_json.side_effect = _map_layer_then([[_make_feature()]], product)
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()

    records = dl.download_by_date_range(MAP_LAYER_URL, dt.datetime(2026, 9, 15), dt.datetime(2026, 9, 15))

    assert records[0]["avalanche_size"] == "3"


@patch("downloader.base.BaseDownloader._get_json")
def test_download_leaves_the_size_empty_for_a_day_outside_the_product(mock_get_json):
    product = _make_product("3", published="2026-09-10T14:35:00+00:00", expires="2026-09-12T14:00:00+00:00")
    mock_get_json.side_effect = _map_layer_then([[_make_feature()]], product)
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()

    records = dl.download_by_date_range(MAP_LAYER_URL, dt.datetime(2026, 9, 15), dt.datetime(2026, 9, 15))

    assert records[0]["avalanche_size"] == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "FeatureCollection", "features": []},
        None,
    ],
)
@patch("downloader.base.BaseDownloader._get_json")
def test_download_empty_or_no_data(mock_get_json, payload):
    mock_get_json.return_value = payload
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
    mock_get_json.side_effect = _map_layer_then([[feature1], [feature2]])
    dl = AvalancheOrgDownloader.__new__(AvalancheOrgDownloader)
    dl.logger = MagicMock()
    start = dt.datetime(2026, 9, 14)
    end = dt.datetime(2026, 9, 15)
    records = dl.download_by_date_range(MAP_LAYER_URL, start, end)
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
