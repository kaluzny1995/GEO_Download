import argparse
import csv
import datetime as dt
import logging
import os
import sys

import downloader  # noqa: F401 - triggers downloader registrations
import util
from downloader.base import BaseDownloader
from downloader_factory import get_downloader
from model import AppConfig, LoadParams, SourceConfig


def parse_args(config: AppConfig) -> argparse.Namespace:
    """Parses command line arguments"""
    source_names = [name for name, src in config.sources.items() if src.enabled]
    parser = argparse.ArgumentParser(description="GIS Data Downloader Python 3.11 application.")

    parser.add_argument(
        "source", type=str, choices=source_names, help=f"data source to download, available: {source_names}"
    )

    return parser.parse_args()


def create_folders(source: SourceConfig):
    """Creates folders for data if not exist"""
    if not os.path.exists(source.output_folder):
        os.makedirs(source.output_folder)


def show_params(source_name: str, source: SourceConfig, load_params: LoadParams, logger: logging.Logger) -> None:
    """Shows the parameters and its values"""
    print("Source name:", source_name)
    print("Source type:", source.type)
    print("API URL:", source.api_url)
    print("Output folder:", source.output_folder)
    print("Output file pattern:", source.output_file_pattern)
    print("Load type:", load_params.load_type.value)
    print("Start date:", load_params.date_from)
    print("End date:", load_params.date_to, "\n")

    logger.info(f"Source name: {source_name}")
    logger.info(f"Source type: {source.type}")
    logger.info(f"API URL: {source.api_url}")
    logger.info(f"Output folder: {source.output_folder}")
    logger.info(f"Output file pattern: {source.output_file_pattern}")
    logger.info(f"Load type: {load_params.load_type.value}")
    logger.info(f"Start date: {load_params.date_from}")
    logger.info(f"End date: {load_params.date_to}")


def save_csv(
    data: list[dict], output_folder: str, output_file_pattern: str, date: dt.datetime, logger: logging.Logger
) -> bool:
    """Saves data to CSV file. Returns True only when a file was actually written."""
    output_file = output_file_pattern.format(date=date.strftime("%Y-%m-%d"))
    output_path = f"{output_folder}/{output_file}"

    if not data:
        logger.warning(f"No data to save for {date.strftime('%Y-%m-%d')}.")
        print(f"No data to save for {date.strftime('%Y-%m-%d')}.")
        return False

    fieldnames = data[0].keys()

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"File {output_path} saved. Records: {len(data)}.")
        logger.info(f"File {output_path} saved. Records: {len(data)}.")
    except Exception as e:
        logger.error(f"Error saving CSV: {e}")
        print(f"Error saving CSV: {e}")
        return False

    return True


def download_source(
    source: SourceConfig, source_name: str, load_params: LoadParams, dl: BaseDownloader, logger: logging.Logger
) -> None:
    """Downloads every day of the load range and saves it as CSV, then asks the
    downloader for its auxiliary files (source-specific references the ETL joins).

    Raises RuntimeError when the run produced no files at all (nothing to
    ingest) — the process then ends with exit code 1, which stops the chain
    in GEO_E2E so INGESTION/DATA_QUALITY are skipped.
    """
    saved_files = 0

    for date in util.date_range(load_params.date_from, load_params.date_to):
        print(f"Downloading data for {date.strftime('%Y-%m-%d')}.")
        logger.info(f"Downloading data for {date.strftime('%Y-%m-%d')}.")

        # Download data for the specific day
        next_date = date + dt.timedelta(days=1)
        data = dl.download_by_date_range(source.api_url, date, next_date)

        # Save to CSV
        if save_csv(data, source.output_folder, source.output_file_pattern, date, logger=logger):
            saved_files += 1

    if saved_files == 0:
        message = (
            f"No files downloaded for {source_name} in "
            f"{load_params.date_from.strftime('%Y-%m-%d')}..{load_params.date_to.strftime('%Y-%m-%d')} — "
            "nothing to ingest."
        )
        logger.error(message)
        raise RuntimeError(message)

    # Reference files the ETL joins next to the day CSVs (best effort: the data of this run
    # is written already, so a failure here is logged instead of failing the download).
    try:
        dl.ensure_auxiliary_files(source.api_url)
    except Exception as error:
        message = f"Auxiliary files of {source_name} could not be created: {error}"
        logger.error(message)
        print(f"ERROR: {message}", flush=True)

    print("\nDone.")
    logger.info("Done.")


def main() -> int:
    # Load config
    config = AppConfig.from_json()

    # Parse arguments
    args = parse_args(config)

    # Get source config
    source_name = args.source
    source = config.get_source_by_name(source_name)

    # Setup logger
    logger = util.setup_logger(
        name=f"download_{source_name}",
        log_file=f"logs/{source_name}/download_{source_name}_{dt.datetime.now().isoformat()}.log",
    )

    print(f"---- {source_name} Downloader ----\n")
    logger.info(f"---- {source_name} Downloader ----")

    # Determine load type and date range
    load_params = LoadParams.from_source(source)

    # Show parameters
    show_params(source_name, source, load_params, logger=logger)

    if load_params.date_from > load_params.date_to:
        message = "Recent file date is bigger than end date. Nothing to download."
        print(message)
        logger.info(message)
        print("\nDone.")
        logger.info("Done.")
        return 0

    # Create folders if not exist
    create_folders(source)

    # Initialize downloader based on source type
    dl = get_downloader(source.type, logger=logger, **source.params)

    # Download data for each day in the date range (raises when nothing was written)
    download_source(source, source_name, load_params, dl, logger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
