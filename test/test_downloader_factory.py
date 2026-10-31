import pytest

from downloader_factory import DownloaderFactory, get_downloader
from model.e_source_type import ESourceType


class MockDownloader:
    def __init__(self, logger=None):
        self.logger = logger


class AnotherMockDownloader:
    def __init__(self, logger=None):
        self.logger = logger


@pytest.fixture(autouse=True)
def clear_registry():
    """Clears downloader registry before each test"""
    DownloaderFactory.clear()
    yield
    DownloaderFactory.clear()


@pytest.mark.parametrize(
    "source_type",
    [
        ESourceType.USGS_EARTHQUAKE,
        ESourceType.GDACS,
        ESourceType.EONET,
        ESourceType.OPENMETEO_FLOOD,
        ESourceType.USGS_NWIS,
    ],
)
def test_register_and_create(source_type):
    # Arrange
    DownloaderFactory.register(source_type, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(source_type)

    # Assert
    assert isinstance(downloader, MockDownloader)


def test_create_with_kwargs():
    # Arrange
    DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.USGS_EARTHQUAKE, logger="test_logger")

    # Assert
    assert downloader.logger == "test_logger"


def test_create_unregistered_type():
    # Arrange
    # Act & Assert
    with pytest.raises(ValueError, match="No downloader registered"):
        DownloaderFactory.create(ESourceType.USGS_EARTHQUAKE)


def test_get_downloader():
    # Arrange
    DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, MockDownloader)

    # Act
    downloader = get_downloader("usgs_earthquake")

    # Assert
    assert isinstance(downloader, MockDownloader)


def test_get_downloader_invalid_type():
    # Arrange
    # Act & Assert
    with pytest.raises(ValueError):
        get_downloader("invalid_type")


def test_register_overwrite():
    # Arrange
    DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, MockDownloader)
    DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, AnotherMockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.USGS_EARTHQUAKE)

    # Assert
    assert isinstance(downloader, AnotherMockDownloader)
