from __future__ import annotations

import csv
import datetime as dt
import logging
import os
from pathlib import Path
from typing import ClassVar, TypedDict

import requests

from downloader.base import BaseDownloader
from reverse_geocode import stamp_geocode

DEFAULT_NOTICE_API_URL = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice"
DEFAULT_NCEI_API_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes"
DEFAULT_NCEI_PAGE_SIZE = 200

NCEI_REFERENCE_FIELDS = [
    "id",
    "vnum",
    "volcano_name",
    "year",
    "month",
    "day",
    "vei",
    "deaths",
    "injuries",
    "missing",
    "houses_destroyed",
    "damage_millions_dollars",
]
NCEI_STAMPED_COLUMNS = ["vei", "casualties", "damage"]


class _NceiAgg(TypedDict):
    """Per-volcano totals over every significant eruption row."""

    volcano_name: str
    vei: float | None
    deaths: float
    deaths_seen: bool
    damage: float
    damage_seen: bool


def _ncei_float(value: str | float | int | None) -> float | None:
    """One NCEI number as a float, ``None`` when undefined or unusable."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _ncei_number(value: str | float | int | None) -> str:
    """One NCEI number as written into a CSV cell, ``""`` when undefined.

    Args:
        value: A raw API number (``4``, ``14.5``) or anything unusable.

    Returns:
        The number without a trailing ``.0`` for whole numbers (``"4"``,
        ``"14.5"``, ``"5405"``) and ``""`` for ``None``/blank/unparsable.
    """
    number = _ncei_float(value)
    if number is None:
        return ""
    if number.is_integer():
        return str(int(number))
    return str(number)


def _ncei_rank(row: dict) -> tuple[int, int, int, int]:
    """Ordering key of one reference row: ``(year, month, day, id)`` as ints.

    A missing month/day counts as ``0``, so a year-only row sorts before any
    dated row of the same year; ``id`` breaks the remaining ties.
    """

    def _int(key: str) -> int:
        try:
            return int(float(row.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    return (_int("year"), _int("month"), _int("day"), _int("id"))


def _notice_key(notice_identifier: str, vnum: str | int) -> str:
    """Lookup key of one volcano section of one notice: ``"<notice_identifier>|<vnum>"``."""
    return f"{notice_identifier}|{vnum}"


def _parse_notice(data: dict, vnum: str | int) -> dict[str, str]:
    """Extract one volcano's fields from a fetched notice payload.

    Args:
        data: Decoded JSON body of the notice endpoint.
        vnum: Volcano number whose section is wanted — a notice carries one
            section per volcano (plus region-wide sections with no ``vnum``).

    Returns:
        ``notice_type``, ``latitude``, ``longitude``, ``region`` and
        ``synopsis`` as strings; a field the API left out (``None``) becomes
        an empty string, which the ETL turns into ``NULL``.

    Raises:
        RuntimeError: When no section of the notice carries *vnum* (the feed
            row and the notice payload disagree — fail loudly, never guess).
    """
    sections = data.get("notice_sections") or []
    section = next((s for s in sections if str(s.get("vnum") or "") == str(vnum)), None)
    if section is None:
        available = ", ".join(str(s.get("vnum")) for s in sections) or "none"
        raise RuntimeError(
            f"notice {data.get('notice_identifier', '?')} has no section for vnum {vnum} (has: {available})"
        )
    latitude = section.get("lat")
    longitude = section.get("lng")
    return {
        "notice_type": str(data.get("notice_type") or "").strip(),
        "latitude": str(latitude) if latitude is not None else "",
        "longitude": str(longitude) if longitude is not None else "",
        "region": str(section.get("region") or "").strip(),
        "synopsis": str(section.get("synopsis") or "").strip(),
    }


class USGSVolcanoDownloader(BaseDownloader):
    """Downloads volcano alert data from the USGS Volcano Hazards Program API.

    Uses the HANS API to get volcanoes with elevated alert levels (Yellow, Orange, Red).
    Only volcanoes above NORMAL/GREEN status are included — these are the
    time-varying entries that change day to day as conditions evolve.

    Covers US-monitored volcanoes across observatories:
    Alaska (AVO), California (CALVO), Cascades (CVO), Hawaiian (HVO),
    Northern Mariana Islands (NMI), and Yellowstone (YVO).

    The feed only carries the notice's headline fields — the coordinates,
    region, status line and full notice type of each volcano live behind the
    notice endpoint and are resolved here at download time: every record gets
    ``notice_type_name``, ``latitude``, ``longitude``, ``region`` and
    ``synopsis`` from the consolidated lookup ``data/usgs_volcano_notices.csv``
    (``notice_identifier, vnum, notice_type, latitude, longitude, region,
    synopsis``), fetched once per new notice (a notice covers all of its
    volcanoes) and persisted for every later run, so the ETL reads the details
    straight from the source row. Notices are immutable once published, so a
    cached entry never goes stale. Records without an identifier or volcano
    number get empty values, which the ETL turns into ``NULL``.

    Each volcano point is also reverse-geocoded once into ``geocode_state``
    (the shared lookup ``data/reverse_geocode.csv``), the subdivision the ETL
    used to resolve itself.

    On top of the notice fields, every record is stamped with the volcano's
    record in the NCEI/WDS Significant Volcanic Eruptions Database, combined
    over all of its significant eruptions (``vei`` = highest VEI,
    ``casualties`` = total deaths, ``damage`` = total damage in millions of
    USD — all three empty for a volcano NCEI does not list, e.g. Great
    Sitkin). The whole database is kept once in
    ``data/usgs_volcano_ncei_eruptions.csv`` (built on first use from the NCEI
    HazEL endpoint, eruption rows only) and looked up by ``vnum`` against NCEI's
    ``volcanoLocationNewNum`` — the same Smithsonian GVP volcano number.
    """

    DEFAULT_NOTICES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "usgs_volcano_notices.csv")
    DEFAULT_NCEI_FILE = str(Path(__file__).resolve().parent.parent / "data" / "usgs_volcano_ncei_eruptions.csv")
    NOTICES_FIELDS: ClassVar[list[str]] = [
        "notice_identifier",
        "vnum",
        "notice_type",
        "latitude",
        "longitude",
        "region",
        "synopsis",
    ]
    notices_file: str | None = None

    def __init__(
        self,
        timeout: int = 30,
        logger: logging.Logger | None = None,
        log_folder: str | None = None,
        notices_file: str | None = None,
        reverse_geocode_file: str | None = None,
        ncei_eruptions_file: str | None = None,
        notice_api_url: str = DEFAULT_NOTICE_API_URL,
        ncei_api_url: str = DEFAULT_NCEI_API_URL,
        ncei_page_size: int = DEFAULT_NCEI_PAGE_SIZE,
    ):
        super().__init__(
            timeout=timeout, logger=logger, log_folder=log_folder, reverse_geocode_file=reverse_geocode_file
        )
        if ncei_page_size <= 0:
            raise ValueError("ncei_page_size must be positive")
        self.notices_file = notices_file or self.DEFAULT_NOTICES_FILE
        self.ncei_eruptions_file = ncei_eruptions_file or self.DEFAULT_NCEI_FILE
        self.notice_api_url = notice_api_url
        self.ncei_api_url = ncei_api_url
        self.ncei_page_size = ncei_page_size
        self._ncei: dict[str, dict[str, str]] | None = None

    @staticmethod
    def _build_record(volcano: dict) -> dict:
        """Extract a flat record dict from a volcano status entry.

        The five notice-detail keys are empty placeholders here —
        :meth:`_resolve_notices` fills them from the lookup once the whole
        range is downloaded (the keys must already exist to keep the CSV
        column order).
        """
        return {
            "volcano_name": volcano.get("volcano_name", ""),
            "vnum": volcano.get("vnum", ""),
            "observatory": volcano.get("obs_abbr", ""),
            "observatory_name": volcano.get("obs_fullname", ""),
            "alert_level": volcano.get("alert_level", ""),
            "color_code": volcano.get("color_code", ""),
            "notice_type": volcano.get("notice_type_cd", ""),
            "notice_identifier": volcano.get("notice_identifier", ""),
            "notice_date": volcano.get("sent_utc", ""),
            "notice_url": volcano.get("notice_url", ""),
            "notice_data_url": volcano.get("notice_data", ""),
            "notice_type_name": "",
            "latitude": "",
            "longitude": "",
            "region": "",
            "synopsis": "",
        }

    def _load_notices(self) -> dict[str, dict[str, str]]:
        """Read the lookup CSV into ``notice_key -> {field: value}``.

        Returns:
            One entry per stored ``(notice, vnum)`` pair; a missing file
            yields an empty lookup and malformed rows keep empty answers.
        """
        if not self.notices_file or not os.path.exists(self.notices_file):
            return {}
        with open(self.notices_file, newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(handle)
            return {
                _notice_key(row["notice_identifier"], row["vnum"]): {
                    field: (row.get(field) or "").strip() for field in self.NOTICES_FIELDS[2:]
                }
                for row in rows
            }

    def _save_notices(self, mapping: dict[str, dict[str, str]]) -> None:
        """Write the full lookup back to :attr:`notices_file`, sorted by key."""
        if not self.notices_file:
            return
        os.makedirs(os.path.dirname(self.notices_file) or ".", exist_ok=True)
        with open(self.notices_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.NOTICES_FIELDS)
            for key in sorted(mapping):
                notice_identifier, vnum = key.rsplit("|", 1)
                values = mapping[key]
                writer.writerow(
                    [
                        notice_identifier,
                        vnum,
                        values["notice_type"],
                        values["latitude"],
                        values["longitude"],
                        values["region"],
                        values["synopsis"],
                    ]
                )

    def _fetch_notice(self, notice_identifier: str) -> dict:
        """Download the payload of a single notice.

        Args:
            notice_identifier: The notice's DOI identifier.

        Returns:
            The decoded JSON body.

        Raises:
            RuntimeError: When the request fails or the body is not a JSON
                object (no network, HTTP error, bad body).
        """
        try:
            with self.session.get(f"{self.notice_api_url}/{notice_identifier}", timeout=self.timeout) as response:
                response.raise_for_status()
                data = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"volcano notice request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"volcano notice {notice_identifier} returned a non-JSON body") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"volcano notice {notice_identifier} returned no payload")
        return data

    def _resolve_notices(self, records: list[dict]) -> None:
        """Stamp the notice details onto every record of a download.

        Every distinct ``(notice_identifier, vnum)`` pair of *records* is
        resolved against :attr:`notices_file`; a notice the lookup does not
        cover yet is fetched once (however many of its volcanoes appear) and
        persisted. Records with a blank identifier or volcano number get empty
        values — the same result the ETL used to compute when it had no entry.

        Raises:
            RuntimeError: When one or more new pairs could not be fetched or a
                notice payload has no section for the requested volcano.
                Successful answers are still persisted, failed ones retry on
                the next run (same strict policy the ETL applied).
        """
        if not records:
            return

        pairs = {
            _notice_key(identifier, vnum)
            for identifier, vnum in (
                (str(record.get("notice_identifier") or "").strip(), str(record.get("vnum") or "").strip())
                for record in records
            )
            if identifier and vnum
        }
        mapping = self._load_notices()
        missing = sorted(pairs - mapping.keys())
        if missing:
            self.logger.info(
                f"Volcano notices: {len(missing)} pair(s) missing from {self.notices_file} — querying the API..."
            )
            payloads: dict[str, dict] = {}
            failures: list[str] = []
            fetched = 0
            for key in missing:
                notice_identifier, vnum = key.rsplit("|", 1)
                try:
                    if notice_identifier not in payloads:
                        payloads[notice_identifier] = self._fetch_notice(notice_identifier)
                    mapping[key] = _parse_notice(payloads[notice_identifier], vnum)
                except Exception as exc:
                    failures.append(f"{key} ({exc})")
                else:
                    fetched += 1
            if fetched:
                self._save_notices(mapping)
                self.logger.info(f"  notice lookup: {fetched} fetched, {len(mapping)} total → {self.notices_file}")
            if failures:
                raise RuntimeError(
                    f"volcano notice fetch failed for {len(failures)} of {len(missing)} new pair(s): "
                    f"{'; '.join(failures[:3])}" + ("…" if len(failures) > 3 else "")
                )

        for record in records:
            identifier = str(record.get("notice_identifier") or "").strip()
            vnum = str(record.get("vnum") or "").strip()
            values = mapping.get(_notice_key(identifier, vnum), {}) if identifier and vnum else {}
            record["notice_type_name"] = values.get("notice_type", "")
            record["latitude"] = values.get("latitude", "")
            record["longitude"] = values.get("longitude", "")
            record["region"] = values.get("region", "")
            record["synopsis"] = values.get("synopsis", "")
        self.logger.info(f"  notice lookup resolved {len(pairs & mapping.keys())} of {len(pairs)} distinct pairs")

    def _fetch_ncei(self) -> None:
        """Download the whole NCEI significant-eruption database into the reference CSV.

        Pages through the NCEI HazEL endpoint, keeps the eruption rows only
        (the database also carries non-eruption volcano events such as
        significant earthquakes) and writes them sorted by volcano number and
        date. A partial download never overwrites the reference: without a
        complete database the run fails loudly instead of stamping holes.

        Raises:
            RuntimeError: When a page cannot be fetched or the database came
                back empty.
        """
        collected: list[dict[str, str]] = []
        page = 1
        while True:
            data = self._get_json(f"{self.ncei_api_url}?size={self.ncei_page_size}&page={page}")
            if not isinstance(data, dict):
                raise RuntimeError(f"NCEI eruption fetch failed on page {page} ({self.ncei_api_url})")
            for item in data.get("items") or []:
                if not item.get("eruption"):
                    continue
                collected.append(
                    {
                        "id": str(item.get("id") or ""),
                        "vnum": str(item.get("volcanoLocationNewNum") or ""),
                        "volcano_name": str(item.get("name") or ""),
                        "year": str(item.get("year") or ""),
                        "month": str(item.get("month") or ""),
                        "day": str(item.get("day") or ""),
                        "vei": _ncei_number(item.get("vei")),
                        "deaths": _ncei_number(item.get("deaths")),
                        "injuries": _ncei_number(item.get("injuries")),
                        "missing": _ncei_number(item.get("missing")),
                        "houses_destroyed": _ncei_number(item.get("housesDestroyed")),
                        "damage_millions_dollars": _ncei_number(item.get("damageMillionsDollars")),
                    }
                )
            if page >= int(data.get("totalPages") or 1):
                break
            page += 1
        if not collected:
            raise RuntimeError(f"NCEI eruption database came back empty ({self.ncei_api_url})")

        folder = os.path.dirname(self.ncei_eruptions_file)
        if folder:
            os.makedirs(folder, exist_ok=True)
        collected.sort(key=lambda row: (row["vnum"], _ncei_rank(row)))
        with open(self.ncei_eruptions_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=NCEI_REFERENCE_FIELDS)
            writer.writeheader()
            writer.writerows(collected)
        self.logger.info(f"NCEI eruption reference: {len(collected)} rows → {self.ncei_eruptions_file}")

    def _load_ncei(self) -> dict[str, dict[str, str]]:
        """The reference CSV aggregated per volcano, ``vnum →`` stamped numbers.

        Returns:
            One entry per volcano NCEI lists, combined over all of its
            significant eruptions: ``vei`` is the highest VEI the volcano
            ever reached, ``deaths`` (stamped as ``casualties``) and
            ``damage_millions_dollars`` (stamped as ``damage``) are the sums
            over its eruption rows. A field no eruption of that volcano
            reports stays empty and an unknown volcano gets no entry — the
            stamped columns then stay empty and the ETL turns them into
            ``NULL``.
        """
        if self._ncei is None:
            if not (os.path.exists(self.ncei_eruptions_file) and os.path.getsize(self.ncei_eruptions_file) > 0):
                self._fetch_ncei()
            totals: dict[str, _NceiAgg] = {}
            if os.path.exists(self.ncei_eruptions_file):
                with open(self.ncei_eruptions_file, newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        vnum = (row.get("vnum") or "").strip()
                        if not vnum:
                            continue
                        agg = totals.setdefault(
                            vnum,
                            {
                                "volcano_name": (row.get("volcano_name") or "").strip(),
                                "vei": None,
                                "deaths": 0.0,
                                "deaths_seen": False,
                                "damage": 0.0,
                                "damage_seen": False,
                            },
                        )
                        vei = _ncei_float(row.get("vei"))
                        max_vei = agg["vei"]
                        if vei is not None and (max_vei is None or vei > max_vei):
                            agg["vei"] = vei
                        deaths = _ncei_float(row.get("deaths"))
                        if deaths is not None:
                            agg["deaths"] = agg["deaths"] + deaths
                            agg["deaths_seen"] = True
                        damage = _ncei_float(row.get("damage_millions_dollars"))
                        if damage is not None:
                            agg["damage"] = agg["damage"] + damage
                            agg["damage_seen"] = True
            self._ncei = {
                vnum: {
                    "volcano_name": agg["volcano_name"],
                    "vei": _ncei_number(agg["vei"]),
                    "deaths": _ncei_number(agg["deaths"]) if agg["deaths_seen"] else "",
                    "damage_millions_dollars": _ncei_number(agg["damage"]) if agg["damage_seen"] else "",
                }
                for vnum, agg in totals.items()
            }
        return self._ncei

    def _stamp_ncei(self, records: list[dict]) -> None:
        """Append the NCEI reference's per-volcano numbers to every record.

        The three columns land after ``geocode_state`` (``vei``, ``casualties``,
        ``damage``): a volcano NCEI does not carry — or a field none of its
        eruptions reports — gets an empty value, which the ETL turns
        into ``NULL``. Every record gets the keys, so the CSV column order
        stays identical across files.
        """
        if not records:
            return
        lookup = self._load_ncei()
        matched = 0
        for record in records:
            row = lookup.get(str(record.get("vnum") or "").strip())
            record["vei"] = row["vei"] if row else ""
            record["casualties"] = row["deaths"] if row else ""
            record["damage"] = row["damage_millions_dollars"] if row else ""
            if row is not None:
                matched += 1
        self.logger.info(f"  NCEI eruption lookup matched {matched} of {len(records)} record(s)")

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download elevated volcano alerts from USGS HANS API for the given date range.

        Only returns volcanoes with alert level above NORMAL (i.e. ADVISORY, WATCH, WARNING).
        Filters by notice_date to include only notices issued within the date range.
        The kept records are enriched with their notice details from
        :attr:`notices_file`, their subdivision from the reverse-geocode
        lookup and their NCEI eruption record (:attr:`ncei_eruptions_file`)
        before returning.
        """
        self.logger.info(f"Downloading USGS Volcano data for {start_date.date()} to {end_date.date()}")

        url = f"{base_url}/getElevatedVolcanoes"
        data = self._get_json(url)
        data = self._validate_list_response(data, "USGS Volcano")
        if not data:
            return []

        start_str = self._format_date(start_date)
        end_str = self._format_date(end_date)

        all_records: list[dict] = []
        for volcano in data:
            record = self._build_record(volcano)
            notice_date = record.get("notice_date", "")
            if notice_date and start_str <= notice_date[:10] <= end_str:
                all_records.append(record)

        self._resolve_notices(all_records)
        stamp_geocode(all_records, output=self.reverse_geocode_file, columns=("geocode_state",), logger=self.logger)
        self._stamp_ncei(all_records)

        self.logger.info(f"Downloaded {len(all_records)} USGS Volcano records total")
        return all_records

    def ensure_auxiliary_files(self, api_url: str) -> None:
        """Build the NCEI eruption reference stamped onto the day CSVs.

        ``data/usgs_volcano_ncei_eruptions.csv`` carries one row per
        significant eruption of the NCEI/WDS database (``vnum`` = Smithsonian
        GVP volcano number, ``vei``, ``deaths``, ``damage_millions_dollars``, …)
        that the downloader joins onto every record at download time. Without
        it the ``vei``/``casualties``/``damage`` columns stay empty, so a run
        that finds it missing builds it from the NCEI HazEL endpoint (one
        paged pull of the whole ~900-row database). An existing reference is
        left alone; delete it to force a refresh.

        Args:
            api_url: HANS endpoint configured for this source (the reference
                comes from NCEI, not from it).
        """
        self.logger.info(
            f"Ensuring NCEI eruption reference {self.ncei_eruptions_file} (NCEI endpoint {self.ncei_api_url})"
        )
        self._load_ncei()
