from enum import StrEnum


class ELoadType(StrEnum):
    HISTORICAL = "HISTORICAL"
    INCREMENTAL = "INCREMENTAL"
