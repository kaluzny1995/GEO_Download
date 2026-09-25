from downloader.avalanche_org import AvalancheOrgDownloader
from downloader.base import BaseDownloader
from downloader.eonet import EONETDownloader
from downloader.gdacs import GDACSDownloader
from downloader.ibtracs import IBTrACSDownloader
from downloader.nifc import NIFCDownloader
from downloader.openmeteo_flood import OpenMeteoFloodDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
from downloader.usgs_nwis import USGSNWISDownloader
from downloader.usgs_volcano import USGSVolcanoDownloader
from downloader_factory import DownloaderFactory
from model.e_source_type import ESourceType

# Register downloaders
DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, USGSEarthquakeDownloader)
DownloaderFactory.register(ESourceType.GDACS, GDACSDownloader)
DownloaderFactory.register(ESourceType.EONET, EONETDownloader)
DownloaderFactory.register(ESourceType.OPENMETEO_FLOOD, OpenMeteoFloodDownloader)
DownloaderFactory.register(ESourceType.USGS_NWIS, USGSNWISDownloader)
DownloaderFactory.register(ESourceType.AVALANCHE_ORG, AvalancheOrgDownloader)
DownloaderFactory.register(ESourceType.IBTRACS, IBTrACSDownloader)
DownloaderFactory.register(ESourceType.USGS_VOLCANO, USGSVolcanoDownloader)
DownloaderFactory.register(ESourceType.NIFC, NIFCDownloader)

__all__ = [
    "AvalancheOrgDownloader",
    "BaseDownloader",
    "EONETDownloader",
    "GDACSDownloader",
    "IBTrACSDownloader",
    "NIFCDownloader",
    "OpenMeteoFloodDownloader",
    "USGSEarthquakeDownloader",
    "USGSNWISDownloader",
    "USGSVolcanoDownloader",
]
