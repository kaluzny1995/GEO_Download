from __future__ import annotations

from typing import ClassVar

from model.e_source_type import ESourceType


class DownloaderFactory:
    """ Factory for creating downloaders based on source type """
    _registry: ClassVar[dict[ESourceType, type]] = {}

    @classmethod
    def register(cls, source_type: ESourceType, downloader_class: type) -> None:
        """ Registers a downloader class for a source type """
        cls._registry[source_type] = downloader_class

    @classmethod
    def create(cls, source_type: ESourceType, **kwargs):
        """ Creates a downloader instance for the given source type """
        if source_type not in cls._registry:
            raise ValueError(f"No downloader registered for source type: {source_type}")
        return cls._registry[source_type](**kwargs)

    @classmethod
    def clear(cls) -> None:
        """ Clears the registry (for testing) """
        cls._registry.clear()


def get_downloader(source_type_str: str, **kwargs):
    """ Helper function to get downloader by source type string """
    source_type = ESourceType(source_type_str)
    return DownloaderFactory.create(source_type, **kwargs)
