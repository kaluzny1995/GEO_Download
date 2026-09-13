from usgs.downloader import USGSDownloader
from downloader_factory import DownloaderFactory
from model.e_source_type import ESourceType

# Register USGS downloader
DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, USGSDownloader)
