from enum import Enum


class ELoadType(str, Enum):
    HISTORICAL = "HISTORICAL"
    INCREMENTAL = "INCREMENTAL"
