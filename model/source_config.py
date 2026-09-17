from pydantic import BaseModel
from typing import Dict, Any


class SourceConfig(BaseModel):
    """ Config for a single data source """
    type: str
    enabled: bool
    api_url: str
    feed_url: str = ""
    start_date: str
    output_folder: str
    output_file_pattern: str
    is_date_to_previous_day: bool = True
    params: Dict[str, Any] = {}

    class ConfigDict:
        frozen = True
