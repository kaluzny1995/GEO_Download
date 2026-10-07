import csv
import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
import requests.exceptions

from downloader.usgs_volcano import (
    NCEI_API_URL,
    NCEI_REFERENCE_FIELDS,
    NCEI_STAMPED_COLUMNS,
    NOTICE_API_URL,
    USGSVolcanoDownloader,
    _ncei_number,
    _notice_key,
    _parse_notice,
)
from test.downloader.conftest import MockLogger

TEST_BASE_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano"
NOTICE_ID = "DOI-USGS-AVO-2026-09-29T18:26:19+00:00"
PAYLOAD = {
    "notice_identifier": NOTICE_ID,
    "notice_type": "Daily Update",
    "notice_sections": [
        {
            "vnum": "311120",
            "vName": "Great Sitkin",
            "lat": 52.0765,
            "lng": -176.1109,
            "region": "Aleutians",
            "synopsis": "AVO Great Sitkin ORANGE/WATCH - Slow eruption of lava continues.",
        },
        {
            "vnum": 311360,
            "vName": "Shishaldin",
            "lat": 54.7554,
            "lng": -163.9711,
            "region": "Aleutians",
            "synopsis": "AVO Shishaldin YELLOW/ADVISORY - Low-level unrest continues.",
        },
        {"vnum": None, "lat": None, "lng": None, "region": None, "synopsis": None},
    ],
}
EXPECTED_COLUMNS = [
    "volcano_name",
    "vnum",
    "observatory",
    "observatory_name",
    "alert_level",
    "color_code",
    "notice_type",
    "notice_identifier",
    "notice_date",
    "notice_url",
    "notice_data_url",
    "notice_type_name",
    "latitude",
    "longitude",
    "region",
    "synopsis",
]


def _downloader(tmp_path, logger=None, ncei_rows=None, reverse_geocode_file=None):
    """Downloader whose NCEI reference lives in *tmp_path* (seeded, never fetched)."""
    reference = tmp_path / "usgs_volcano_ncei_eruptions.csv"
    with open(reference, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NCEI_REFERENCE_FIELDS)
        writer.writeheader()
        for row in ncei_rows or []:
            writer.writerow({field: row.get(field, "") for field in NCEI_REFERENCE_FIELDS})
    return USGSVolcanoDownloader(
        logger=logger or MockLogger(),
        notices_file=str(tmp_path / "usgs_volcano_notices.csv"),
        ncei_eruptions_file=str(reference),
        reverse_geocode_file=reverse_geocode_file,
    )


def _ncei_row(vnum="332010", **overrides):
    row = dict.fromkeys(NCEI_REFERENCE_FIELDS, "")
    row.update({"id": "6864", "vnum": vnum, "volcano_name": "Kilauea", "year": "2018"})
    row.update(overrides)
    return row


def _stored(notice_identifier, vnum, **values):
    mapping = {
        "notice_type": "Daily Update",
        "latitude": "52.0765",
        "longitude": "-176.1109",
        "region": "Aleutians",
        "synopsis": "line",
    }
    mapping.update(values)
    return (_notice_key(notice_identifier, vnum), mapping)


def _record(notice_identifier=NOTICE_ID, vnum="311120", **overrides):
    record = {
        "volcano_name": "Great Sitkin",
        "vnum": vnum,
        "observatory": "avo",
        "observatory_name": "Alaska Volcano Observatory",
        "alert_level": "WATCH",
        "color_code": "ORANGE",
        "notice_type": "DU",
        "notice_identifier": notice_identifier,
        "notice_date": "2026-09-29T18:26:19Z",
        "notice_url": "https://example.org/notice",
        "notice_data_url": "https://example.org/api/notice",
        "notice_type_name": "",
        "latitude": "",
        "longitude": "",
        "region": "",
        "synopsis": "",
    }
    record.update(overrides)
    return record


def test_build_record():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    volcano = {
        "volcano_name": "Great Sitkin",
        "vnum": "1203-01-",
        "obs_abbr": "AVO",
        "obs_fullname": "Alaska Volcano Observatory",
        "alert_level": "ADVISORY",
        "color_code": "YELLOW",
        "notice_type_cd": "VONA",
        "notice_identifier": "VOA030",
        "sent_utc": "2026-09-09T14:30:00Z",
        "notice_url": "https://volcanoes.usgs.gov/vns2/volcano.html?vid=1203010",
    }

    record = downloader._build_record(volcano)

    assert record["volcano_name"] == "Great Sitkin"
    assert record["vnum"] == "1203-01-"
    assert record["observatory"] == "AVO"
    assert record["observatory_name"] == "Alaska Volcano Observatory"
    assert record["alert_level"] == "ADVISORY"
    assert record["color_code"] == "YELLOW"
    assert record["notice_type"] == "VONA"
    assert record["notice_identifier"] == "VOA030"
    assert record["notice_date"] == "2026-09-09T14:30:00Z"
    assert record["notice_url"] == "https://volcanoes.usgs.gov/vns2/volcano.html?vid=1203010"
    assert record["notice_type_name"] == ""
    assert record["latitude"] == ""
    assert record["region"] == ""
    assert record["synopsis"] == ""


def test_build_record_key_order():
    downloader = USGSVolcanoDownloader(logger=MockLogger())

    assert list(downloader._build_record({})) == EXPECTED_COLUMNS


def test_build_record_empty():
    logger = MockLogger()
    downloader = USGSVolcanoDownloader(logger=logger)

    record = downloader._build_record({})

    assert record["volcano_name"] == ""
    assert record["alert_level"] == ""
    assert record["notice_date"] == ""


def test_download_by_date_range_success(tmp_path):
    downloader = _downloader(tmp_path)

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "volcano_name": "Great Sitkin",
            "vnum": "1203-01-",
            "obs_abbr": "AVO",
            "alert_level": "ADVISORY",
            "color_code": "YELLOW",
            "notice_type_cd": "VONA",
            "notice_identifier": "VOA030",
            "sent_utc": "2026-09-09T14:30:00Z",
            "notice_url": "https://example.com/volcano",
        },
        {
            "volcano_name": "Shishaldin",
            "vnum": "1203-02-",
            "obs_abbr": "AVO",
            "alert_level": "WATCH",
            "color_code": "ORANGE",
            "notice_type_cd": "VONA",
            "notice_identifier": "VOA031",
            "sent_utc": "2026-09-10T10:00:00Z",
            "notice_url": "https://example.com/volcano2",
        },
    ]
    mock_response.raise_for_status = MagicMock()
    payload = {
        "notice_type": "Volcano Activity Notification",
        "notice_sections": [
            {"vnum": "1203-01-", "lat": 52.0765, "lng": -176.1109, "region": "Aleutians", "synopsis": "first"},
            {"vnum": "1203-02-", "lat": 54.7554, "lng": -163.9711, "region": "Aleutians", "synopsis": "second"},
        ],
    }

    with (
        patch.object(downloader.session, "get", return_value=mock_response),
        patch.object(downloader, "_fetch_notice", return_value=payload) as mocked_fetch,
    ):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 17))

    assert len(result) == 2
    assert result[0]["volcano_name"] == "Great Sitkin"
    assert result[1]["volcano_name"] == "Shishaldin"
    assert mocked_fetch.call_count == 2
    assert result[0]["notice_type_name"] == "Volcano Activity Notification"
    assert result[0]["latitude"] == "52.0765"
    assert result[1]["region"] == "Aleutians"
    assert result[0]["synopsis"] == "first"
    assert downloader._load_notices() and len(downloader._load_notices()) == 2


def test_download_by_date_range_filters_by_date(tmp_path):
    downloader = _downloader(tmp_path)

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "volcano_name": "Volcano A",
            "sent_utc": "2026-09-01T10:00:00Z",
        },
        {
            "volcano_name": "Volcano B",
            "sent_utc": "2026-09-10T10:00:00Z",
        },
    ]
    mock_response.raise_for_status = MagicMock()

    with (
        patch.object(downloader.session, "get", return_value=mock_response),
        patch.object(downloader, "_fetch_notice") as mocked_fetch,
    ):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 5), dt.datetime(2026, 9, 12))

    assert len(result) == 1
    assert result[0]["volcano_name"] == "Volcano B"
    mocked_fetch.assert_not_called()
    assert result[0]["notice_type_name"] == ""
    assert result[0]["latitude"] == ""


def test_download_by_date_range_empty(tmp_path):
    logger = MockLogger()
    downloader = _downloader(tmp_path, logger=logger)

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 17))

    assert len(result) == 0
    assert any("No data received" in msg for _, msg in logger.messages)


def test_download_by_date_range_none_response(tmp_path):
    downloader = _downloader(tmp_path)

    mock_response = MagicMock()
    mock_response.json.return_value = None
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, "get", return_value=mock_response):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 17))

    assert len(result) == 0


def test_download_by_date_range_connection_error(tmp_path):
    logger = MockLogger()
    downloader = _downloader(tmp_path, logger=logger)

    with patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 2))

    assert result == []
    assert any("Failed to fetch" in msg for _, msg in logger.messages)


class TestNoticeKey:
    def test_joins_identifier_and_vnum(self):
        assert _notice_key(NOTICE_ID, "311120") == f"{NOTICE_ID}|311120"

    def test_int_vnum_matches_string_vnum(self):
        assert _notice_key(NOTICE_ID, 311120) == _notice_key(NOTICE_ID, "311120")


class TestParseNotice:
    def test_extracts_the_matching_section(self):
        fields = _parse_notice(PAYLOAD, "311120")

        assert fields == {
            "notice_type": "Daily Update",
            "latitude": "52.0765",
            "longitude": "-176.1109",
            "region": "Aleutians",
            "synopsis": "AVO Great Sitkin ORANGE/WATCH - Slow eruption of lava continues.",
        }

    def test_int_vnum_matches_string_section(self):
        assert _parse_notice(PAYLOAD, 311360)["latitude"] == "54.7554"

    def test_null_section_fields_become_empty_strings(self):
        payload = {
            "notice_identifier": NOTICE_ID,
            "notice_type": None,
            "notice_sections": [{"vnum": "284141", "lat": None, "lng": None, "region": None, "synopsis": None}],
        }

        fields = _parse_notice(payload, "284141")

        assert fields == {"notice_type": "", "latitude": "", "longitude": "", "region": "", "synopsis": ""}

    def test_missing_section_raises(self):
        with pytest.raises(RuntimeError, match="no section for vnum 999999"):
            _parse_notice(PAYLOAD, "999999")


class TestDefaultNoticesFile:
    def test_points_into_data_folder(self):
        downloader = USGSVolcanoDownloader(logger=MockLogger())

        assert downloader.notices_file == USGSVolcanoDownloader.DEFAULT_NOTICES_FILE
        assert downloader.notices_file.endswith("usgs_volcano_notices.csv")
        assert f"data{__import__('os').sep}" in downloader.notices_file


class TestLookupFile:
    def test_save_then_load(self, tmp_path):
        downloader = _downloader(tmp_path)
        mapping = dict([_stored(NOTICE_ID, "311120")])

        downloader._save_notices(mapping)

        assert downloader._load_notices() == mapping

    def test_missing_file_is_empty(self, tmp_path):
        assert _downloader(tmp_path)._load_notices() == {}

    def test_save_creates_the_data_folder(self, tmp_path):
        downloader = USGSVolcanoDownloader(logger=MockLogger(), notices_file=str(tmp_path / "new" / "notices.csv"))

        downloader._save_notices(dict([_stored(NOTICE_ID, "311120")]))

        assert downloader._load_notices()


class TestFetchNotice:
    def test_returns_the_json_body(self, tmp_path):
        downloader = _downloader(tmp_path)
        response = MagicMock()
        response.json.return_value = PAYLOAD

        with patch.object(downloader.session, "get", return_value=response) as mocked:
            assert downloader._fetch_notice(NOTICE_ID) == PAYLOAD

        mocked.assert_called_once()
        assert mocked.call_args.args[0] == f"{NOTICE_API_URL}/{NOTICE_ID}"

    def test_connection_error_raises_runtime_error(self, tmp_path):
        downloader = _downloader(tmp_path)

        with (
            patch.object(downloader.session, "get", side_effect=requests.exceptions.ConnectionError("refused")),
            pytest.raises(RuntimeError, match="volcano notice request failed"),
        ):
            downloader._fetch_notice(NOTICE_ID)

    def test_non_json_body_raises_runtime_error(self, tmp_path):
        downloader = _downloader(tmp_path)
        response = MagicMock()
        response.json.side_effect = ValueError("no json")

        with (
            patch.object(downloader.session, "get", return_value=response),
            pytest.raises(RuntimeError, match="non-JSON body"),
        ):
            downloader._fetch_notice(NOTICE_ID)

    def test_non_object_body_raises_runtime_error(self, tmp_path):
        downloader = _downloader(tmp_path)
        response = MagicMock()
        response.json.return_value = [1, 2]

        with (
            patch.object(downloader.session, "get", return_value=response),
            pytest.raises(RuntimeError, match="returned no payload"),
        ):
            downloader._fetch_notice(NOTICE_ID)


class TestResolveNotices:
    def test_fully_cached_pairs_never_fetch(self, tmp_path):
        downloader = _downloader(tmp_path)
        downloader._save_notices(dict([_stored(NOTICE_ID, "311120", latitude="1")]))
        records = [_record()]

        with patch.object(downloader, "_fetch_notice") as mocked:
            downloader._resolve_notices(records)

        mocked.assert_not_called()
        assert records[0]["latitude"] == "1"
        assert records[0]["notice_type_name"] == "Daily Update"

    def test_fetches_each_notice_once_for_many_volcanoes(self, tmp_path):
        downloader = _downloader(tmp_path)
        records = [_record(vnum="311120"), _record(vnum="311360")]

        with patch.object(downloader, "_fetch_notice", return_value=PAYLOAD) as mocked:
            downloader._resolve_notices(records)

        assert mocked.call_count == 1
        mocked.assert_called_once_with(NOTICE_ID)
        assert records[0]["latitude"] == "52.0765"
        assert records[1]["latitude"] == "54.7554"
        assert set(downloader._load_notices()) == {_notice_key(NOTICE_ID, "311120"), _notice_key(NOTICE_ID, "311360")}

    def test_failed_fetch_raises_but_successes_are_cached(self, tmp_path):
        downloader = _downloader(tmp_path)
        bad = "DOI-USGS-NMI-2026-09-24T20:22:11+00:00"

        def _fetch(identifier):
            if "AVO" in identifier:
                return PAYLOAD
            raise RuntimeError("no network")

        with (
            patch.object(downloader, "_fetch_notice", side_effect=_fetch),
            pytest.raises(RuntimeError, match="volcano notice fetch failed for 1"),
        ):
            downloader._resolve_notices([_record(), _record(notice_identifier=bad, vnum="284141")])

        stored = downloader._load_notices()
        assert _notice_key(NOTICE_ID, "311120") in stored
        assert _notice_key(bad, "284141") not in stored

    def test_bad_payload_counts_as_a_failure(self, tmp_path):
        downloader = _downloader(tmp_path)

        with (
            patch.object(downloader, "_fetch_notice", return_value=PAYLOAD),
            pytest.raises(RuntimeError, match="no section for vnum"),
        ):
            downloader._resolve_notices([_record(vnum="999999")])

        assert downloader._load_notices() == {}

    def test_records_without_keys_get_empty_values(self, tmp_path):
        downloader = _downloader(tmp_path)
        records = [_record(notice_identifier="", vnum=""), _record(notice_identifier=NOTICE_ID, vnum="")]

        with patch.object(downloader, "_fetch_notice") as mocked:
            downloader._resolve_notices(records)

        mocked.assert_not_called()
        for record in records:
            assert record["notice_type_name"] == ""
            assert record["latitude"] == ""
            assert record["synopsis"] == ""

    def test_empty_records_are_a_noop(self, tmp_path):
        downloader = _downloader(tmp_path)

        downloader._resolve_notices([])

        assert downloader._load_notices() == {}


def test_download_stamps_geocode_state(tmp_path):
    """Every notice coordinate is reverse-geocoded into geocode_state."""
    lookup = str(tmp_path / "reverse_geocode.csv")
    downloader = _downloader(tmp_path, reverse_geocode_file=lookup)

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "volcano_name": "Great Sitkin",
            "vnum": "1203-01-",
            "obs_abbr": "AVO",
            "alert_level": "ADVISORY",
            "color_code": "YELLOW",
            "notice_type_cd": "VONA",
            "notice_identifier": "VOA030",
            "sent_utc": "2026-09-09T14:30:00Z",
            "notice_url": "https://example.com/volcano",
        }
    ]
    mock_response.raise_for_status = MagicMock()
    payload = {
        "notice_type": "Volcano Activity Notification",
        "notice_sections": [
            {"vnum": "1203-01-", "lat": 52.0765, "lng": -176.1109, "region": "Aleutians", "synopsis": "first"},
        ],
    }

    with (
        patch.object(downloader.session, "get", return_value=mock_response),
        patch.object(downloader, "_fetch_notice", return_value=payload),
    ):
        result = downloader.download_by_date_range(TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 17))

    assert len(result) == 1
    assert result[0]["geocode_state"] == "MT"
    assert "geocode_country" not in result[0]


class TestNceiNumber:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (4, "4"),
            (4.0, "4"),
            (385.5, "385.5"),
            (None, ""),
            ("", ""),
            ("14.5", "14.5"),
            ("n/a", ""),
            (float("nan"), ""),
        ],
    )
    def test_formats_numbers_for_the_csv(self, value, expected):
        assert _ncei_number(value) == expected


class TestNceiReference:
    def test_default_file_points_into_data_folder(self):
        downloader = USGSVolcanoDownloader(logger=MockLogger())

        assert downloader.ncei_eruptions_file == USGSVolcanoDownloader.DEFAULT_NCEI_FILE
        assert downloader.ncei_eruptions_file.endswith("usgs_volcano_ncei_eruptions.csv")
        assert f"data{__import__('os').sep}" in downloader.ncei_eruptions_file

    def test_load_aggregates_max_vei_and_sums(self, tmp_path):
        downloader = _downloader(
            tmp_path,
            ncei_rows=[
                _ncei_row(id="1", year="1823", vei="2", damage_millions_dollars="10.5"),
                _ncei_row(id="2", year="1990", vei="4", deaths="5", damage_millions_dollars=""),
                _ncei_row(id="3", year="2018", vei="", deaths="1", damage_millions_dollars="2.5"),
            ],
        )

        (entry,) = downloader._load_ncei().values()

        assert entry["vei"] == "4"
        assert entry["deaths"] == "6"
        assert entry["damage_millions_dollars"] == "13"

    def test_volcano_without_a_field_stays_empty(self, tmp_path):
        downloader = _downloader(tmp_path, ncei_rows=[_ncei_row(id="1", year="1856", vei="3")])

        entry = downloader._load_ncei()["332010"]

        assert entry["vei"] == "3"
        assert entry["deaths"] == ""
        assert entry["damage_millions_dollars"] == ""

    def test_rows_without_a_vnum_are_skipped(self, tmp_path):
        downloader = _downloader(tmp_path, ncei_rows=[_ncei_row(vnum="", volcano_name="Piparo", vei="2")])

        assert downloader._load_ncei() == {}

    def test_missing_file_is_fetched_once(self, tmp_path):
        downloader = USGSVolcanoDownloader(logger=MockLogger(), ncei_eruptions_file=str(tmp_path / "missing.csv"))

        with patch.object(downloader, "_fetch_ncei") as mocked:
            downloader._load_ncei()
            downloader._load_ncei()

        mocked.assert_called_once()


class TestFetchNcei:
    @staticmethod
    def _page(items, page, total_pages):
        return {"items": items, "page": page, "totalPages": total_pages}

    def test_pages_through_the_database_and_skips_non_eruptions(self, tmp_path):
        reference = tmp_path / "ncei.csv"
        downloader = USGSVolcanoDownloader(logger=MockLogger(), ncei_eruptions_file=str(reference))
        first = {
            "id": 2,
            "volcanoLocationNewNum": 332010,
            "name": "Kilauea",
            "year": 1990,
            "month": 3,
            "day": 1,
            "vei": 4,
            "deaths": 5,
            "damageMillionsDollars": 10.5,
            "eruption": True,
        }
        second = [
            {
                "id": 3,
                "volcanoLocationNewNum": 311360,
                "name": "Shishaldin",
                "year": 1856,
                "vei": None,
                "eruption": True,
            },
            {"id": 4, "volcanoLocationNewNum": 999999, "name": "Other", "year": 2000, "eruption": False},
        ]

        with patch.object(downloader, "_get_json", side_effect=[self._page([first], 1, 2), self._page(second, 2, 2)]):
            downloader._fetch_ncei()

        with open(reference, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert list(rows[0]) == NCEI_REFERENCE_FIELDS
        assert len(rows) == 2  # the non-eruption row is never stored
        by_vnum = {row["vnum"]: row for row in rows}
        assert by_vnum["332010"]["vei"] == "4"
        assert by_vnum["332010"]["deaths"] == "5"
        assert by_vnum["332010"]["damage_millions_dollars"] == "10.5"
        assert by_vnum["311360"]["vei"] == ""

    def test_a_failed_page_raises_and_keeps_nothing(self, tmp_path):
        reference = tmp_path / "ncei.csv"
        downloader = USGSVolcanoDownloader(logger=MockLogger(), ncei_eruptions_file=str(reference))

        with (
            patch.object(downloader, "_get_json", return_value=None),
            pytest.raises(RuntimeError, match="NCEI eruption fetch failed"),
        ):
            downloader._fetch_ncei()

        assert not reference.exists()

    def test_an_empty_database_raises(self, tmp_path):
        downloader = USGSVolcanoDownloader(logger=MockLogger(), ncei_eruptions_file=str(tmp_path / "ncei.csv"))

        with (
            patch.object(downloader, "_get_json", return_value=self._page([], 1, 1)),
            pytest.raises(RuntimeError, match="came back empty"),
        ):
            downloader._fetch_ncei()


class TestStampNcei:
    def test_appends_the_three_columns_with_values(self, tmp_path):
        downloader = _downloader(
            tmp_path, ncei_rows=[_ncei_row(vei="4", deaths="5411", damage_millions_dollars="385.5")]
        )
        records = [{"vnum": "332010", "synopsis": "line"}, {"vnum": "311120"}]

        downloader._stamp_ncei(records)

        assert records[0]["vei"] == "4"
        assert records[0]["casualties"] == "5411"
        assert records[0]["damage"] == "385.5"
        assert records[1]["vei"] == ""
        assert records[1]["casualties"] == ""
        assert records[1]["damage"] == ""

    def test_records_without_a_vnum_get_empty_values(self, tmp_path):
        downloader = _downloader(tmp_path, ncei_rows=[_ncei_row(vei="4")])
        records = [{"vnum": ""}]

        downloader._stamp_ncei(records)

        assert records[0]["vei"] == ""

    def test_empty_records_never_touch_the_reference(self, tmp_path):
        downloader = _downloader(tmp_path)

        with patch.object(downloader, "_load_ncei") as mocked:
            downloader._stamp_ncei([])

        mocked.assert_not_called()

    def test_download_stamps_the_columns_after_geocode_state(self, tmp_path):
        downloader = _downloader(
            tmp_path,
            ncei_rows=[_ncei_row(vnum="1203-01-", vei="4", deaths="5411", damage_millions_dollars="385.5")],
        )
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "volcano_name": "Great Sitkin",
                "vnum": "1203-01-",
                "obs_abbr": "AVO",
                "alert_level": "ADVISORY",
                "color_code": "YELLOW",
                "notice_type_cd": "VONA",
                "notice_identifier": "VOA030",
                "sent_utc": "2026-09-09T14:30:00Z",
                "notice_url": "https://example.com/volcano",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        payload = {
            "notice_type": "Volcano Activity Notification",
            "notice_sections": [{"vnum": "1203-01-", "lat": 52.0765, "lng": -176.1109, "region": "Aleutians"}],
        }

        with (
            patch.object(downloader.session, "get", return_value=mock_response),
            patch.object(downloader, "_fetch_notice", return_value=payload),
        ):
            (record,) = downloader.download_by_date_range(
                TEST_BASE_URL, dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 17)
            )

        assert list(record)[-3:] == NCEI_STAMPED_COLUMNS
        assert record["vei"] == "4"
        assert record["casualties"] == "5411"
        assert record["damage"] == "385.5"


class TestEnsureAuxiliaryFiles:
    def test_an_existing_reference_is_not_refetched(self, tmp_path):
        downloader = _downloader(tmp_path, ncei_rows=[_ncei_row()])

        with patch.object(downloader, "_get_json") as mocked:
            downloader.ensure_auxiliary_files(TEST_BASE_URL)

        mocked.assert_not_called()
        assert downloader._load_ncei()["332010"]["volcano_name"] == "Kilauea"

    def test_a_missing_reference_is_built_from_the_endpoint(self, tmp_path):
        reference = tmp_path / "ncei.csv"
        downloader = USGSVolcanoDownloader(logger=MockLogger(), ncei_eruptions_file=str(reference))
        page = {
            "items": [
                {
                    "id": 7,
                    "volcanoLocationNewNum": 332010,
                    "name": "Kilauea",
                    "year": 2018,
                    "vei": 1,
                    "eruption": True,
                }
            ],
            "page": 1,
            "totalPages": 1,
        }

        with patch.object(downloader, "_get_json", return_value=page):
            downloader.ensure_auxiliary_files(TEST_BASE_URL)

        assert reference.exists()
        assert downloader._load_ncei()["332010"]["vei"] == "1"

    def test_the_default_endpoint_is_the_ncei_hazel_api(self):
        downloader = USGSVolcanoDownloader(logger=MockLogger())

        assert downloader.ncei_api_url == NCEI_API_URL
        assert downloader.ncei_api_url.endswith("/hazard-service/api/v1/volcanoes")
