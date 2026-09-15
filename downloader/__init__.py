from downloader.base import BaseDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
from downloader.usgs_volcano import USGSVolcanoDownloader
from downloader_factory import DownloaderFactory
from model.e_source_type import ESourceType

# Register downloaders
DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, USGSEarthquakeDownloader)
DownloaderFactory.register(ESourceType.USGS_VOLCANO_ALERTS, USGSVolcanoDownloader)

__all__ = [
    "BaseDownloader",
    "USGSEarthquakeDownloader",
    "USGSVolcanoDownloader",
]
