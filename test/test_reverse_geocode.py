import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from reverse_geocode import (
    MAX_FETCH_ATTEMPTS,
    USER_AGENT,
    coord_key,
    geocode_map,
    load_cache,
    parse_response,
    reverse_geocode,
    save_cache,
    stamp_geocode,
)


class TestCoordKey:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (45.45251, -104.46729, "45.4525,-104.4673"),
            ("45.4525", "-104.4672", "45.4525,-104.4672"),
            (1.0, 2.0, "1.0000,2.0000"),
        ],
    )
    def test_coord_key(self, lat, lon, expected):
        assert coord_key(lat, lon) == expected


class TestParseResponse:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            ({"address": {"country_code": "us", "ISO3166-2-lvl4": "US-MT"}}, ("US", "MT")),
            ({"address": {"country_code": "mx", "ISO3166-2-lvl4": "MX-GRO"}}, ("MX", "GRO")),
            (
                {"address": {"country_code": "us", "ISO3166-2-lvl4": "US-TX", "ISO3166-2-lvl6": "US-48167"}},
                ("US", "TX"),
            ),
            ({"address": {"country_code": "de", "ISO3166-2-lvl6": "DE-03115"}}, ("DE", "03115")),
            ({"address": {}}, ("", "")),
            ({"address": {"country_code": "aq"}}, ("AQ", "")),
            ({}, ("", "")),
        ],
    )
    def test_parse_response(self, data, expected):
        assert parse_response(data) == expected


class TestReverseGeocode:
    @patch("reverse_geocode.urllib.request.urlopen")
    def test_queries_the_api_and_parses_the_answer(self, mock_urlopen):
        body = json.dumps({"address": {"country_code": "mx", "ISO3166-2-lvl4": "MX-GRO"}}).encode()
        mock_urlopen.return_value = BytesIO(body)

        assert reverse_geocode(17.0, -99.0) == ("MX", "GRO")

        request = mock_urlopen.call_args.args[0]
        assert "lat=17.0" in request.full_url
        assert "lon=-99.0" in request.full_url
        assert "format=jsonv2" in request.full_url
        assert USER_AGENT in request.headers.values()

    @patch("reverse_geocode.urllib.request.urlopen")
    def test_custom_endpoint(self, mock_urlopen):
        mock_urlopen.return_value = BytesIO(b"{}")

        reverse_geocode(1.0, 2.0, api_url="https://example.org/reverse")

        assert mock_urlopen.call_args.args[0].full_url.startswith("https://example.org/reverse?")

    @staticmethod
    def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://example.org/reverse", code, "err", headers or {}, BytesIO(b""))

    @patch("reverse_geocode.time.sleep")
    @patch("reverse_geocode.urllib.request.urlopen")
    def test_transient_rate_limit_is_retried_until_it_succeeds(self, mock_urlopen, _sleep):
        body = json.dumps({"address": {"country_code": "us", "ISO3166-2-lvl4": "US-TX"}}).encode()
        mock_urlopen.side_effect = [self._http_error(429, {"Retry-After": "3"}), BytesIO(body)]

        assert reverse_geocode(30.0, -97.0) == ("US", "TX")

        assert mock_urlopen.call_count == 2

    @patch("reverse_geocode.time.sleep")
    @patch("reverse_geocode.urllib.request.urlopen")
    def test_non_transient_http_error_is_not_retried(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = self._http_error(404)

        with pytest.raises(urllib.error.HTTPError):
            reverse_geocode(30.0, -97.0)

        mock_urlopen.assert_called_once()

    @patch("reverse_geocode.time.sleep")
    @patch("reverse_geocode.urllib.request.urlopen")
    def test_persistent_transient_error_raises_after_the_retry_budget(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = self._http_error(429)

        with pytest.raises(urllib.error.HTTPError):
            reverse_geocode(30.0, -97.0)

        assert mock_urlopen.call_count == MAX_FETCH_ATTEMPTS


class TestCacheFile:
    def test_missing_cache_is_empty(self, tmp_path):
        assert load_cache(str(tmp_path / "missing.csv")) == {}

    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "reverse_geocode.csv")
        mapping = {"45.4525,-104.4672": ("US", "MT"), "15.1433,-104.7983": ("", "")}

        assert save_cache(mapping, path) == 2
        assert load_cache(path) == mapping

    def test_creates_the_cache_directory(self, tmp_path):
        path = str(tmp_path / "cache" / "reverse_geocode.csv")

        save_cache({"1.0000,2.0000": ("US", "TX")}, path)

        assert load_cache(path) == {"1.0000,2.0000": ("US", "TX")}


class TestGeocodeMap:
    @patch("reverse_geocode.reverse_geocode")
    def test_all_cached_skips_the_api(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")
        save_cache({"45.4525,-104.4672": ("US", "MT")}, path)

        mapping = geocode_map([(45.45251, -104.4672)], output=path)

        assert mapping == {"45.4525,-104.4672": ("US", "MT")}
        mock_lookup.assert_not_called()

    @patch("reverse_geocode.reverse_geocode")
    def test_missing_points_are_fetched_and_cached(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")
        mock_lookup.return_value = ("US", "MT")

        mapping = geocode_map([(45.45251, -104.4672), (41.5175, -117.7421)], output=path)

        assert mapping == {"45.4525,-104.4672": ("US", "MT"), "41.5175,-117.7421": ("US", "MT")}
        assert load_cache(path) == mapping
        assert mock_lookup.call_count == 2

    @patch("reverse_geocode.reverse_geocode")
    def test_points_sharing_a_key_are_fetched_once(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")
        mock_lookup.return_value = ("US", "MT")

        geocode_map([(1.0, 2.0), (1.00001, 2.00001)], output=path)

        mock_lookup.assert_called_once()

    @patch("reverse_geocode.reverse_geocode")
    def test_failed_fetch_raises_but_keeps_the_successes(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")
        mock_lookup.side_effect = [("US", "MT"), OSError("no network")]

        with pytest.raises(RuntimeError, match="reverse geocode failed for 1 of 2"):
            geocode_map([(1.0, 2.0), (3.0, 4.0)], output=path)

        assert load_cache(path) == {"1.0000,2.0000": ("US", "MT")}

    @patch("reverse_geocode.reverse_geocode")
    def test_all_failed_fetch_raises_without_writing(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")
        mock_lookup.side_effect = OSError("no network")

        with pytest.raises(RuntimeError, match="reverse geocode failed for 1 of 1"):
            geocode_map([(1.0, 2.0)], output=path)

        assert not (tmp_path / "cache.csv").exists()

    @patch("reverse_geocode.reverse_geocode")
    def test_no_points_returns_the_cache_without_writing(self, mock_lookup, tmp_path):
        path = str(tmp_path / "cache.csv")

        assert geocode_map([], output=path) == {}

        mock_lookup.assert_not_called()
        assert not (tmp_path / "cache.csv").exists()


class TestStampGeocode:
    @staticmethod
    def _seed(tmp_path, *entries: tuple[str, str, str, str]) -> str:
        path = str(tmp_path / "reverse_geocode.csv")
        save_cache({coord_key(lat, lon): (country, state) for lat, lon, country, state in entries}, path)
        return path

    @patch("reverse_geocode.reverse_geocode")
    def test_stamps_both_columns_from_the_lookup(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"))
        records = [{"latitude": "40.0", "longitude": "-105.0"}]

        stamp_geocode(records, output=path)

        assert records[0]["geocode_country"] == "US"
        assert records[0]["geocode_state"] == "CO"
        mock_lookup.assert_not_called()

    @patch("reverse_geocode.reverse_geocode")
    def test_fetch_filter_decides_which_points_reach_the_api(self, mock_lookup, tmp_path):
        path = str(tmp_path / "reverse_geocode.csv")
        mock_lookup.return_value = ("US", "MT")
        records = [
            {"latitude": "40.0", "longitude": "-105.0", "state": ""},
            {"latitude": "41.0", "longitude": "-106.0", "state": "WY"},
        ]

        stamp_geocode(records, output=path, fetch_filter=lambda record: not record["state"])

        assert mock_lookup.call_count == 1
        assert records[0]["geocode_country"] == "US"
        assert records[0]["geocode_state"] == "MT"
        assert records[1]["geocode_country"] == ""
        assert records[1]["geocode_state"] == ""

    @patch("reverse_geocode.reverse_geocode")
    def test_embed_all_stamps_cached_answers_for_filtered_out_records(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"), ("41.0", "-106.0", "US", "WY"))
        records = [
            {"latitude": "40.0", "longitude": "-105.0", "dist": "10"},
            {"latitude": "41.0", "longitude": "-106.0", "dist": "5000"},
        ]

        stamp_geocode(records, output=path, fetch_filter=lambda record: int(record["dist"]) <= 100, embed_all=True)

        assert records[0]["geocode_state"] == "CO"
        assert records[1]["geocode_state"] == "WY"
        mock_lookup.assert_not_called()

    @patch("reverse_geocode.reverse_geocode")
    def test_records_without_usable_coordinates_get_empty_answers(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"))
        records = [
            {"latitude": "", "longitude": ""},
            {"latitude": "not-a-number", "longitude": "-105.0"},
            {"latitude": None, "longitude": None},
        ]

        stamp_geocode(records, output=path)

        assert all(record["geocode_country"] == "" and record["geocode_state"] == "" for record in records)
        mock_lookup.assert_not_called()

    @patch("reverse_geocode.reverse_geocode")
    def test_state_only_sources_stamp_a_single_column(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"))
        records = [{"latitude": "40.0", "longitude": "-105.0"}]

        stamp_geocode(records, output=path, columns=("geocode_state",))

        assert records[0]["geocode_state"] == "CO"
        assert "geocode_country" not in records[0]

    @patch("reverse_geocode.reverse_geocode")
    def test_empty_batch_does_nothing(self, mock_lookup, tmp_path):
        path = str(tmp_path / "reverse_geocode.csv")

        stamp_geocode([], output=path)

        assert not (tmp_path / "reverse_geocode.csv").exists()
        mock_lookup.assert_not_called()

    @patch("reverse_geocode.reverse_geocode")
    def test_unknown_column_is_rejected(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"))

        with pytest.raises(ValueError, match="unknown geocode column"):
            stamp_geocode([{"latitude": "40.0", "longitude": "-105.0"}], output=path, columns=("bogus",))

    @patch("reverse_geocode.reverse_geocode")
    def test_failed_fetch_fails_the_download(self, mock_lookup, tmp_path):
        path = str(tmp_path / "reverse_geocode.csv")
        mock_lookup.side_effect = OSError("no network")

        with pytest.raises(RuntimeError, match="reverse geocode failed for 1 of 1"):
            stamp_geocode([{"latitude": "40.0", "longitude": "-105.0"}], output=path)

    @patch("reverse_geocode.reverse_geocode")
    def test_keys_are_appended_after_the_source_columns(self, mock_lookup, tmp_path):
        path = self._seed(tmp_path, ("40.0", "-105.0", "US", "CO"))
        records = [{"source_col": "x", "latitude": "40.0", "longitude": "-105.0"}]

        stamp_geocode(records, output=path)

        assert list(records[0]) == ["source_col", "latitude", "longitude", "geocode_country", "geocode_state"]
