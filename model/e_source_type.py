from enum import Enum


class ESourceType(str, Enum):
    USGS_EARTHQUAKE = "usgs_earthquake"
    GDACS = "gdacs"
    EONET = "eonet"
    OPENMETEO_FLOOD = "openmeteo_flood"
    USGS_NWIS = "usgs_nwis"
    AVALANCHE_ORG = "avalanche_org"
    IBTRACS = "ibtracs"
    USGS_VOLCANO = "usgs_volcano"
    NIFC = "nifc"
