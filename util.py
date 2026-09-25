import datetime as dt
import logging
import os


def setup_logger(name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
    """ Setup logger — avoids duplicate handlers when called multiple times
        with the same name (e.g. periodic Celery task invocations). """
    log_file_folder: str = os.path.dirname(log_file)
    if log_file_folder and not os.path.exists(log_file_folder):
        os.makedirs(log_file_folder)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Only add a handler if one pointing to the *same* file doesn't already exist.
    # This prevents the handler leak that occurs when setup_logger is called
    # repeatedly (e.g. every Celery task invocation with the same source name).
    existing_paths = {
        os.path.abspath(h.baseFilename)
        for h in logger.handlers
        if isinstance(h, logging.FileHandler)
    }
    if os.path.abspath(log_file) not in existing_paths:
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)

    return logger


def get_recent_file_date(folder_path: str) -> dt.datetime | None:
    """ Returns the latest file date from the output folder (for INCREMENTAL load) """
    if not os.path.exists(folder_path):
        return None

    file_names = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
    if not file_names:
        return None

    dates = []
    for file_name in file_names:
        try:
            date_str = file_name.split("_")[-1].split(".")[0]
            dates.append(dt.datetime.strptime(date_str, "%Y-%m-%d"))
        except (IndexError, ValueError):
            continue

    if not dates:
        return None

    return max(dates)


def date_range(start_date: dt.datetime, end_date: dt.datetime):
    """ Yields consecutive days from start_date to end_date """
    current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    while current <= end:
        yield current
        current += dt.timedelta(days=1)
