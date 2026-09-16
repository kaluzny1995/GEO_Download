from downloader.base import BaseDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
from downloader.gdacs import GDACSDownloader
from downloader.eonet import EONETDownloader
from downloader_factory import DownloaderFactory
from model.e_source_type import ESourceType

# Register downloaders
DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, USGSEarthquakeDownloader)
DownloaderFactory.register(ESourceType.GDACS, GDACSDownloader)
DownloaderFactory.register(ESourceType.EONET, EONETDownloader)

__all__ = [
    "BaseDownloader",
    "USGSEarthquakeDownloader",
    "GDACSDownloader",
    "EONETDownloader",
]
