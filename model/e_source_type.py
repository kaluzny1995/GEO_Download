from enum import Enum


class ESourceType(str, Enum):
    USGS_EARTHQUAKE = "usgs_earthquake"
    USGS_VOLCANO_ALERTS = "usgs_volcano_alerts"
