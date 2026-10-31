"""Build the Open-Meteo/GloFAS discharge threshold reference for GEO_ETL.

The daily flood files say what the discharge *was*; this reference says what
counts as high for a river. For every river in ``data/rivers.json`` the
GloFAS record the Flood API serves (from ``--baseline-start``, 2026-09-01 by
default — the same day the project's data starts — to today) is pulled in one
request per river and reduced to self-computed percentiles — ``Q50``, ``Q90``,
``Q95`` and ``Q99`` of the daily mean discharge, over the days that actually
carry a value.

GEO_ETL joins the resulting CSV on ``river_name`` + ``country`` and writes the
reference into ``other_metrics`` (and the ``danger_rating`` ``Q95``/``Q99``
labels) of ``geo.openmeteo_flood_etl``, see
``single_etl/openmeteo_flood_etl.py``.

Usage::

    python run_openmeteo_thresholds.py
    python run_openmeteo_thresholds.py --baseline-start 2016-01-01 --min-days 730

``python run_download.py OpenMeteo_Flood`` runs this build by itself when the
output file is missing, so the script is what you reach for to *refresh* the
reference — it reads the rows already on disk and only queries the rivers they
do not cover (``--restart`` discards them and pulls every river again).

The Flood API charges a full-history pull heavily and answers a run that goes
too fast with ``429`` *hourly* request limits, so the fetcher asks for
``river_discharge`` only (the ensemble statistics are not used here), paces
itself with ``--sleep``, waits out the clock hour when the API says the limit
is reached and writes every finished row straight to the output file — a run
that is interrupted, or gives up for the night, resumes from the rows already
on disk (``--restart`` starts over).

Re-run it occasionally — the percentiles describe the record up to the day of
the run (the API serves data up to today).
"""

import argparse
import csv
import datetime as dt
import logging
import math
import os
import sys
import time
from collections.abc import Callable

from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from downloader.openmeteo_flood import OpenMeteoFloodDownloader
from model import AppConfig, SourceConfig
from util import setup_logger

SOURCE_NAME = "OpenMeteo_Flood"

DEFAULT_OUTPUT = "data/openmeteo_discharge_thresholds.csv"
"""Reference CSV written by default — ``params.thresholds_file`` in ``config.json``."""

DEFAULT_RIVERS_FILE = "data/rivers.json"
"""River definitions used by default — ``params.rivers_file`` in ``config.json``."""

DEFAULT_BASELINE_START = "2026-09-01"
"""First baseline day: the day the project's data starts."""

DEFAULT_MIN_DAYS = 30
"""Rivers with fewer valid days in the baseline get no percentile row."""

DEFAULT_SLEEP = 1.0
"""Seconds between two river requests — the API throttles full-history pulls."""

PERCENTILES: tuple[int, ...] = (50, 90, 95, 99)
"""Percentiles written to the reference, as ``discharge_pNN_m3s`` columns."""

FIELDNAMES: list[str] = [
    "river_name",
    "country",
    "latitude",
    "longitude",
    "baseline_days",
    "baseline_start",
    "baseline_end",
    *(f"discharge_p{point}_m3s" for point in PERCENTILES),
]
"""Columns of the reference CSV — GEO_ETL relies on this exact order."""


def _seconds_until_next_hour() -> float:
    """Seconds until the next clock hour (UTC), plus a small buffer."""
    now = dt.datetime.now(dt.UTC)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    return (next_hour - now).total_seconds() + 5.0


def _baseline_url(api_url: str, river: dict, start: dt.datetime, end: dt.datetime) -> str:
    """Baseline request URL asking for the discharge series alone.

    The ensemble statistics would quintuple the response for values this
    script never reads, and a full-history pull is what the API charges most
    for — see :func:`make_fetcher`.

    Args:
        api_url: Flood API endpoint.
        river: River definition to query.
        start: First baseline day.
        end: Last baseline day.

    Returns:
        The request URL.
    """
    return (
        f"{api_url}"
        f"?latitude={river['latitude']}"
        f"&longitude={river['longitude']}"
        f"&daily=river_discharge"
        f"&start_date={start.strftime('%Y-%m-%d')}"
        f"&end_date={end.strftime('%Y-%m-%d')}"
    )


def read_thresholds(path: str) -> list[dict]:
    """Rows already written to the output file — the resume set.

    Args:
        path: Reference CSV to read.

    Returns:
        One dict per complete row, in file order; an empty list when the file
        does not exist yet.

    Raises:
        ValueError: When an existing file carries different columns — writing
            into it would mix two formats GEO_ETL cannot read.
    """
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDNAMES:
            raise ValueError(f"{path} has columns {reader.fieldnames} instead of {', '.join(FIELDNAMES)}")
        return [row for row in reader if all(row.get(field) for field in FIELDNAMES)]


def without_429_retry(session: Session) -> Session:
    """Let ``429`` through instead of retrying it — the script waits the hour out.

    The base class retries ``429`` five times with backoff, which hammers the
    API for a minute and still fails once the hourly limit is in effect.

    Args:
        session: Session of the downloader.

    Returns:
        The same session, re-mounted to retry server errors only.
    """
    retries = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def make_fetcher(
    downloader: OpenMeteoFloodDownloader,
    api_url: str,
    start: dt.datetime,
    end: dt.datetime,
    logger: logging.Logger,
    sleep: float = 1.0,
    max_hour_waits: int = 6,
) -> Callable[[dict], dict | None]:
    """Fetch one river's baseline, pacing itself and waiting out ``429``.

    Args:
        downloader: Downloader whose session and timeout to use.
        api_url: Flood API endpoint.
        start: First baseline day.
        end: Last baseline day.
        logger: Logger for failures and limit waits.
        sleep: Seconds to pause after every answered request.
        max_hour_waits: How many clock hours to wait out before giving up.

    Returns:
        A callable taking a river definition and returning its response dict,
        or ``None`` when the request failed.
    """
    session = without_429_retry(downloader.session)

    def fetch(river: dict) -> dict | None:
        url = _baseline_url(api_url, river, start, end)
        for _ in range(max_hour_waits + 1):
            try:
                with session.get(url, timeout=downloader.timeout) as response:
                    if response.status_code == 429:
                        wait = _seconds_until_next_hour()
                        logger.warning(f"Hourly API request limit reached — waiting {wait:.0f}s for the next hour")
                        print(
                            f"  Hourly API request limit reached — waiting {round(wait)}s for the next hour...",
                            flush=True,
                        )
                        time.sleep(wait)
                        continue
                    time.sleep(sleep)
                    try:
                        response.raise_for_status()
                        data = response.json()
                    except (RequestException, ValueError) as error:
                        logger.error(f"Failed to fetch {url}: {error}")
                        return None
                    return data if isinstance(data, dict) else None
            except RequestException as error:
                logger.error(f"Failed to fetch {url}: {error}")
                return None
        logger.error(f"Hourly API request limit still in effect — giving up on {river['name']}")
        return None

    return fetch


def parse_args(source: SourceConfig) -> argparse.Namespace:
    """Parse command line arguments — the paths default to ``source.params``.

    Args:
        source: The ``OpenMeteo_Flood`` section of ``config.json``, whose
            ``rivers_file`` / ``thresholds_file`` params name the two files
            this script reads and writes.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Build the Open-Meteo flood discharge threshold reference.")
    parser.add_argument(
        "--rivers-file",
        default=source.params.get("rivers_file", DEFAULT_RIVERS_FILE),
        help="river definitions (from config.json)",
    )
    parser.add_argument(
        "--output",
        default=source.params.get("thresholds_file", DEFAULT_OUTPUT),
        help="reference CSV to write (read by GEO_ETL through config.json)",
    )
    parser.add_argument("--baseline-start", default=DEFAULT_BASELINE_START, help="first day of the baseline record")
    parser.add_argument("--baseline-end", default=None, help="last day of the baseline record (default: today)")
    parser.add_argument(
        "--min-days",
        type=int,
        default=DEFAULT_MIN_DAYS,
        help="skip rivers with fewer valid days than this (no reliable percentile)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP,
        help="seconds to pause between two river requests (the API throttles full-history pulls)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="ignore rows already in the output file and pull every river again",
    )
    return parser.parse_args()


def percentile(sorted_values: list[float], point: float) -> float:
    """Linear-interpolated percentile of an already sorted sample.

    Args:
        sorted_values: Non-empty ascending sample of baseline discharges.
        point: Percentile in ``[0, 1]``.

    Returns:
        The interpolated value; a single-value sample returns that value.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * point
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def build_row(river: dict, data: dict, min_days: int) -> dict | None:
    """Reduce one river's baseline response to its percentile row.

    Args:
        river: River definition the response was requested for.
        data: Open-Meteo Flood API response for the baseline range.
        min_days: Minimum number of valid days a river needs to be kept.

    Returns:
        The reference row, or ``None`` when the API returned no usable series
        (a river without discharge data, or a baseline shorter than
        *min_days*).
    """
    daily = data.get("daily", {})
    pairs = [
        (day, value)
        for day, value in zip(daily.get("time", []), daily.get("river_discharge", []), strict=False)
        if value is not None
    ]
    if len(pairs) < min_days:
        return None

    values = sorted(value for _, value in pairs)
    row: dict[str, object] = {
        "river_name": river["name"],
        "country": river["country"],
        "latitude": river["latitude"],
        "longitude": river["longitude"],
        "baseline_days": len(values),
        "baseline_start": pairs[0][0],
        "baseline_end": pairs[-1][0],
    }
    for point in PERCENTILES:
        row[f"discharge_p{point}_m3s"] = round(percentile(values, point / 100), 2)
    return row


def build_thresholds(
    downloader: OpenMeteoFloodDownloader,
    api_url: str,
    baseline_start: str,
    baseline_end: str,
    min_days: int,
    logger: logging.Logger,
    *,
    fetch: Callable[[dict], dict | None] | None = None,
    existing: list[dict] | None = None,
    on_row: Callable[[list[dict]], None] | None = None,
) -> list[dict]:
    """Pull the baseline of every river and reduce it to reference rows.

    Args:
        downloader: Downloader providing the river list and the API session.
        api_url: Flood API endpoint.
        baseline_start: First baseline day (``YYYY-MM-DD``).
        baseline_end: Last baseline day (``YYYY-MM-DD``).
        min_days: Minimum valid days per river.
        logger: Logger for progress and per-river failures.
        fetch: Request callable, one river at a time — the default queries
            ``api_url`` through the downloader (see :func:`make_fetcher` for
            the throttled one).
        existing: Rows of an interrupted run; their rivers are not queried
            again and they keep their place at the front of the result.
        on_row: Called with the full row list after every river that added
            one, so the output file survives a killed run.

    Returns:
        One reference row per river with enough baseline data, in river order.
    """
    start = dt.datetime.strptime(baseline_start, "%Y-%m-%d")
    end = dt.datetime.strptime(baseline_end, "%Y-%m-%d")
    logger.info(f"Building discharge thresholds from {baseline_start} to {baseline_end}")
    print(
        f"Building discharge thresholds for {len(downloader._rivers)} rivers ({baseline_start}..{baseline_end})...",
        flush=True,
    )

    query = fetch if fetch is not None else (lambda river: downloader._query_river(api_url, river, start, end))
    rows: list[dict] = list(existing or [])
    done = {(row["river_name"], row["country"]) for row in rows}
    skipped = 0
    resumed = 0
    for index, river in enumerate(downloader._rivers, 1):
        if (river["name"], river["country"]) in done:
            resumed += 1
            continue
        data = query(river)
        row = build_row(river, data or {}, min_days) if data and isinstance(data, dict) else None
        if row is None:
            skipped += 1
            logger.warning(f"No usable baseline for {river['name']} ({river['country']})")
        else:
            rows.append(row)
            if on_row is not None:
                on_row(rows)

        if index % 20 == 0:
            print(f"  {index}/{len(downloader._rivers)} rivers processed...", flush=True)
            logger.info(f"  Progress: {index}/{len(downloader._rivers)} rivers queried")

    logger.info(f"Built {len(rows)} reference rows, skipped {skipped}")
    resume_note = f", resumed {resumed} from the output file" if resumed else ""
    print(
        f"Reference rows: {len(rows)} (skipped {skipped} rivers without {min_days}+ valid days{resume_note})",
        flush=True,
    )
    return rows


def write_thresholds(rows: list[dict], output_path: str) -> None:
    """Write the reference CSV (header first, even for an empty result).

    Args:
        rows: Reference rows from :func:`build_thresholds`.
        output_path: CSV file to write.
    """
    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"File {output_path} saved. Records: {len(rows)}.")


def main() -> int:
    """Build the reference from the rivers of the configured source."""
    config = AppConfig.from_json()
    source = config.get_source_by_name(SOURCE_NAME)
    args = parse_args(source)

    logger = setup_logger(
        name=f"thresholds_{SOURCE_NAME}",
        log_file=f"logs/{SOURCE_NAME}/thresholds_{SOURCE_NAME}_{dt.datetime.now().isoformat()}.log",
    )
    logger.info(f"---- {SOURCE_NAME} threshold reference started ----")

    baseline_end = args.baseline_end or dt.date.today().isoformat()
    downloader = OpenMeteoFloodDownloader(logger=logger, rivers_file=args.rivers_file)

    existing = [] if args.restart else read_thresholds(args.output)
    if existing:
        print(f"Resuming: {len(existing)} river(s) already in {args.output}", flush=True)
        logger.info(f"Resuming from {len(existing)} rows already in {args.output}")

    start = dt.datetime.strptime(args.baseline_start, "%Y-%m-%d")
    end = dt.datetime.strptime(baseline_end, "%Y-%m-%d")
    fetch = make_fetcher(downloader, source.api_url, start, end, logger, sleep=args.sleep)
    rows = build_thresholds(
        downloader,
        source.api_url,
        args.baseline_start,
        baseline_end,
        args.min_days,
        logger,
        fetch=fetch,
        existing=existing,
        on_row=lambda current: write_thresholds(current, args.output),
    )
    write_thresholds(rows, args.output)

    logger.info("Done.")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
