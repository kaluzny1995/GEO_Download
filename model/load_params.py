import datetime as dt

from pydantic import BaseModel, ConfigDict

import util
from model.e_load_type import ELoadType
from model.source_config import SourceConfig


class LoadParams(BaseModel):
    load_type: ELoadType
    date_from: dt.datetime
    date_to: dt.datetime

    model_config = ConfigDict(frozen=True)

    @staticmethod
    def from_source(source: SourceConfig) -> "LoadParams":
        recent_date = util.get_recent_file_date(source.output_folder)
        start_date = dt.datetime.strptime(source.start_date, "%Y-%m-%d")

        return LoadParams(
            load_type=ELoadType.HISTORICAL if recent_date is None else ELoadType.INCREMENTAL,
            date_from=start_date if recent_date is None else recent_date + dt.timedelta(days=1),
            date_to=dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
            if source.is_date_to_previous_day
            else dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
        )
