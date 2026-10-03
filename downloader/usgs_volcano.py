from __future__ import annotations

import csv
import datetime as dt
import logging
import os
from pathlib import Path
from typing import ClassVar

import requests

from downloader.base import BaseDownloader

NOTICE_API_URL = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice"


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
    """

    DEFAULT_NOTICES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "usgs_volcano_notices.csv")
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
    ):
        super().__init__(timeout=timeout, logger=logger, log_folder=log_folder)
        self.notices_file = notices_file or self.DEFAULT_NOTICES_FILE

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
            response = self.session.get(f"{NOTICE_API_URL}/{notice_identifier}", timeout=self.timeout)
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

    def download_by_date_range(self, base_url: str, start_date: dt.datetime, end_date: dt.datetime) -> list[dict]:
        """Download elevated volcano alerts from USGS HANS API for the given date range.

        Only returns volcanoes with alert level above NORMAL (i.e. ADVISORY, WATCH, WARNING).
        Filters by notice_date to include only notices issued within the date range.
        The kept records are enriched with their notice details from
        :attr:`notices_file` before returning.
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

        self.logger.info(f"Downloaded {len(all_records)} USGS Volcano records total")
        return all_records
