from downloader.base import BaseDownloader
from downloader.usgs_earthquake import USGSEarthquakeDownloader
from downloader.smithsonian_gvp import SmithsonianGVPDownloader
from downloader_factory import DownloaderFactory
from model.e_source_type import ESourceType

# Register downloaders
DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, USGSEarthquakeDownloader)
DownloaderFactory.register(ESourceType.SMITHSONIAN_GVP, SmithsonianGVPDownloader)

__all__ = [
    "BaseDownloader",
    "USGSEarthquakeDownloader",
    "SmithsonianGVPDownloader",
]
