"""Reverse geocode coordinates to an ISO country/state pair with a cached lookup.

Used by the ``downloader/`` scripts to stamp ``geocode_country`` /
``geocode_state`` onto every source record, so GEO_ETL reads them straight
from the source CSV instead of querying an API at ETL time. The endpoint
(Nominatim / OpenStreetMap, keyless) is queried only for coordinates missing
from the lookup file, which is written back after every run::

    data/reverse_geocode.csv    latitude, longitude, country_code, state_province

Coordinates are keyed at 4 decimal places (~11 m), so a point is queried once
and reused by every later run. Which points of a download need an answer is
each downloader's decision (see ``stamp_geocode``): a coordinate the file
already covers never reaches the API.

Nominatim's usage policy allows at most one request per second from an
identifiable client, so every request waits :data:`REQUEST_DELAY_SECONDS`
first. A coordinate the API answers with no country (open ocean) is cached as
an empty ``country_code`` — that is a real answer, and the ETL turns it into
its fallback ``ZZ``. Requests that fail are *not* cached: they are retried on
the next run, and when nothing could be fetched the download fails instead of
silently leaving holes in the lookup.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

DEFAULT_API_URL = "https://nominatim.openstreetmap.org/reverse"
DEFAULT_REVERSE_GEOCODE_FILE = str(Path(__file__).resolve().parent / "data" / "reverse_geocode.csv")
OUTPUT_FIELDS = ["latitude", "longitude", "country_code", "state_province"]
GEOCODE_COLUMNS = ("geocode_country", "geocode_state")
KEY_DECIMALS = 4
USER_AGENT = "GEO_Download/1.0"
REQUEST_DELAY_SECONDS = 1.1


def coord_key(latitude: float | str, longitude: float | str) -> str:
    """Lookup key of a coordinate: both values rounded to 4 decimals (~11 m).

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.

    Returns:
        ``"<latitude>,<longitude>"`` with both parts fixed to
        :data:`KEY_DECIMALS` decimals.
    """
    return f"{float(latitude):.{KEY_DECIMALS}f},{float(longitude):.{KEY_DECIMALS}f}"


def parse_response(data: dict) -> tuple[str, str]:
    """Turn a Nominatim reverse geocode response into a country/state pair.

    Args:
        data: JSON body of the endpoint (``address.country_code``,
            ``address.ISO3166-2-lvl4``, …).

    Returns:
        ``(country_code, state_province)`` — the ISO 3166-1 alpha-2 country
        and the subdivision part of the most specific ISO 3166-2 code the
        address carries (``US-TX`` → ``TX``); the state level (``lvl4``)
        wins over the district levels below it. Both are empty strings when
        the API found neither: open water has no address at all, and many
        countries' waters have no subdivision.
    """
    address = data.get("address") or {}
    country = str(address.get("country_code") or "").strip().upper()
    state = ""
    for level in ("lvl4", "lvl5", "lvl6"):
        subdivision = str(address.get(f"ISO3166-2-{level}") or "").strip()
        if "-" in subdivision:
            state = subdivision.rsplit("-", 1)[-1]
            break
    return country, state


def reverse_geocode(latitude: float, longitude: float, api_url: str = DEFAULT_API_URL) -> tuple[str, str]:
    """Query the endpoint for one coordinate.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
        api_url: Reverse geocode endpoint.

    Returns:
        ``(country_code, state_province)`` from :func:`parse_response`.

    Raises:
        OSError: When the request fails (no network, HTTP error, bad body).
    """
    time.sleep(REQUEST_DELAY_SECONDS)
    query = urllib.parse.urlencode(
        {
            "lat": float(latitude),
            "lon": float(longitude),
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 14,
            "accept-language": "en",
        }
    )
    request = urllib.request.Request(f"{api_url}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    return parse_response(data)


def load_cache(path: str = DEFAULT_REVERSE_GEOCODE_FILE) -> dict[str, tuple[str, str]]:
    """Read the lookup CSV into ``coord_key -> (country_code, state_province)``.

    Args:
        path: Lookup file to read; a missing file yields an empty cache.

    Returns:
        One entry per stored coordinate; malformed rows keep empty answers.
    """
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as handle:
        return {
            coord_key(row["latitude"], row["longitude"]): (
                (row["country_code"] or "").strip(),
                (row["state_province"] or "").strip(),
            )
            for row in csv.DictReader(handle)
        }


def save_cache(mapping: dict[str, tuple[str, str]], path: str = DEFAULT_REVERSE_GEOCODE_FILE) -> int:
    """Write ``coord_key -> (country_code, state_province)`` back to the lookup.

    Args:
        mapping: Full lookup contents (existing plus newly fetched entries).
        path: Lookup CSV to write; the parent directory is created when missing.

    Returns:
        The number of coordinates written.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OUTPUT_FIELDS)
        for key in sorted(mapping):
            latitude, longitude = key.split(",")
            country, state = mapping[key]
            writer.writerow([latitude, longitude, country, state])
    return len(mapping)


def geocode_map(
    points: Iterable[tuple[float, float]],
    *,
    api_url: str = DEFAULT_API_URL,
    output: str = DEFAULT_REVERSE_GEOCODE_FILE,
    logger: logging.Logger | None = None,
) -> dict[str, tuple[str, str]]:
    """Resolve every coordinate in *points*, fetching only what the lookup misses.

    Args:
        points: ``(latitude, longitude)`` pairs as collected from the records.
        api_url: Reverse geocode endpoint.
        output: Lookup CSV to read and extend.
        logger: Logger for fetch messages; defaults to the module logger.

    Returns:
        ``coord_key -> (country_code, state_province)`` covering every point;
        answers fetched for this call are already persisted to *output*.

    Raises:
        RuntimeError: When one or more new coordinates could not be fetched.
            Successful answers are still cached, failed ones retry next run.
    """
    log = logger or logging.getLogger(__name__)
    mapping = load_cache(output)
    missing = sorted({coord_key(*point) for point in points} - mapping.keys())
    if not missing:
        return mapping

    log.info(f"Reverse geocode: {len(missing)} coordinate(s) missing from {output} — querying the API...")
    failures: list[str] = []
    fetched = 0
    for key in missing:
        latitude, longitude = (float(part) for part in key.split(","))
        try:
            mapping[key] = reverse_geocode(latitude, longitude, api_url)
        except Exception as exc:
            failures.append(f"{key} ({exc})")
        else:
            fetched += 1
    if fetched:
        save_cache(mapping, output)
        log.info(f"Reverse geocode lookup updated: {fetched} fetched, {len(mapping)} total → {output}")
    if failures:
        raise RuntimeError(
            f"reverse geocode failed for {len(failures)} of {len(missing)} new coordinate(s): "
            f"{'; '.join(failures[:3])}" + ("…" if len(failures) > 3 else "")
        )
    return mapping


def stamp_geocode(
    records: list[dict],
    *,
    output: str = DEFAULT_REVERSE_GEOCODE_FILE,
    latitude_key: str = "latitude",
    longitude_key: str = "longitude",
    columns: Sequence[str] = GEOCODE_COLUMNS,
    fetch_filter: Callable[[dict], bool] | None = None,
    embed_all: bool = False,
    api_url: str = DEFAULT_API_URL,
    logger: logging.Logger | None = None,
) -> None:
    """Stamp ``geocode_country``/``geocode_state`` onto every record of a download.

    The keys are appended in iteration order, so they land after the source
    columns of the CSV (``save_csv`` takes the field names from the first
    record). Only the points a download *needs* reach the API:

    Args:
        records: Record dicts as they will be written to the CSV; modified in
            place. An empty batch does nothing.
        output: Lookup CSV to read and extend.
        latitude_key: Record key carrying the latitude.
        longitude_key: Record key carrying the longitude.
        columns: Which of :data:`GEOCODE_COLUMNS` to stamp — the state-only
            sources pass ``("geocode_state",)``.
        fetch_filter: Predicate deciding which records need an API-backed
            answer (``None`` fetches every record with usable coordinates).
            Records outside the filter are stamped from the lookup only when
            *embed_all* is set, otherwise with empty strings — mirroring the
            ETL behaviour this replaces.
        embed_all: Stamp cached answers even for records the filter excludes
            (the shared lookup may already cover them).
        api_url: Reverse geocode endpoint.
        logger: Logger for fetch messages; defaults to the module logger.

    Raises:
        RuntimeError: When a needed coordinate could not be fetched — no
            record is written that day (same strict policy the ETL applied).
    """
    if not records:
        return
    invalid = set(columns) - set(GEOCODE_COLUMNS)
    if invalid:
        raise ValueError(f"unknown geocode column(s): {sorted(invalid)}")

    log = logger or logging.getLogger(__name__)

    def point_of(record: dict) -> tuple[float, float] | None:
        latitude = str(record.get(latitude_key) or "").strip()
        longitude = str(record.get(longitude_key) or "").strip()
        if not latitude or not longitude:
            return None
        try:
            return float(latitude), float(longitude)
        except ValueError:
            return None

    fetch_points = {
        point
        for record in records
        if (point := point_of(record)) is not None and (fetch_filter is None or fetch_filter(record))
    }
    mapping = geocode_map(fetch_points, api_url=api_url, output=output, logger=log)
    fetch_keys = {coord_key(*point) for point in fetch_points}

    for record in records:
        point = point_of(record)
        key = coord_key(*point) if point is not None else None
        country, state = ("", "")
        if key is not None and (key in fetch_keys or embed_all):
            country, state = mapping.get(key, ("", ""))
        if "geocode_country" in columns:
            record["geocode_country"] = country
        if "geocode_state" in columns:
            record["geocode_state"] = state

    log.info(
        f"  reverse geocode stamped {len(columns)} column(s) on {len(records)} record(s) "
        f"({len(fetch_keys)} distinct coordinate(s) ensured)"
    )
