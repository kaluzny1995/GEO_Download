from pydantic import BaseModel, ConfigDict

from model.source_config import SourceConfig


class DownloadParams(BaseModel):
    source: SourceConfig

    model_config = ConfigDict(frozen=True)

    @staticmethod
    def from_source(source: SourceConfig) -> "DownloadParams":
        return DownloadParams(source=source)
