from enum import Enum


class ESourceType(str, Enum):
    USGS_EARTHQUAKE = "usgs_earthquake"
    SMITHSONIAN_GVP = "smithsonian_gvp"
