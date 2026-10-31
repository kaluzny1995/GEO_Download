import json

from pydantic import BaseModel, ConfigDict

from model.source_config import SourceConfig


class AppConfig(BaseModel):
    """App config class"""

    sources: dict[str, SourceConfig]

    model_config = ConfigDict(frozen=True)

    @staticmethod
    def from_json() -> "AppConfig":
        with open("config.json") as f:
            config = AppConfig(**json.load(f))
        return config

    def get_source_by_name(self, name: str) -> SourceConfig:
        """Returns source config by name"""
        if name not in self.sources:
            raise ValueError(f"Source '{name}' not found in config.")
        return self.sources[name]
