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
    """ Clears downloader registry before each test """
    DownloaderFactory.clear()
    yield
    DownloaderFactory.clear()


def test_register_and_create():
    # Arrange
    DownloaderFactory.register(ESourceType.USGS_EARTHQUAKE, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.USGS_EARTHQUAKE)

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


def test_register_gdacs():
    # Arrange
    DownloaderFactory.register(ESourceType.GDACS, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.GDACS)

    # Assert
    assert isinstance(downloader, MockDownloader)


def test_register_eonet():
    # Arrange
    DownloaderFactory.register(ESourceType.EONET, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.EONET)

    # Assert
    assert isinstance(downloader, MockDownloader)


def test_register_openmeteo_flood():
    # Arrange
    DownloaderFactory.register(ESourceType.OPENMETEO_FLOOD, MockDownloader)

    # Act
    downloader = DownloaderFactory.create(ESourceType.OPENMETEO_FLOOD)

    # Assert
    assert isinstance(downloader, MockDownloader)
