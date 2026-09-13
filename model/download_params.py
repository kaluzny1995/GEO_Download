from pydantic import BaseModel

from model.source_config import SourceConfig


class DownloadParams(BaseModel):
    source: SourceConfig

    class ConfigDict:
        frozen = True

    @staticmethod
    def from_source(source: SourceConfig) -> 'DownloadParams':
        return DownloadParams(source=source)
