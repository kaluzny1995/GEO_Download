from enum import Enum


class ESourceType(str, Enum):
    USGS_EARTHQUAKE = "usgs_earthquake"
    GDACS = "gdacs"
    EONET = "eonet"
    OPENMETEO_FLOOD = "openmeteo_flood"
