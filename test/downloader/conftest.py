from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest


class MockLogger(logging.Logger):
    """Shared test logger that records messages for assertion."""

    def __init__(self, name: str = "mock") -> None:
        super().__init__(name)
        self.messages: list[tuple[str, str]] = []

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:
        assert isinstance(msg, str)
        self.messages.append(("INFO", msg))

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:
        assert isinstance(msg, str)
        self.messages.append(("ERROR", msg))

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:
        assert isinstance(msg, str)
        self.messages.append(("WARNING", msg))


@pytest.fixture(autouse=True)
def _isolated_reverse_geocode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every downloader at a throwaway lookup and stub the geocode API.

    Tests must never read or extend the shared ``data/reverse_geocode.csv``:
    a coordinate the real lookup misses would query Nominatim for real and
    persist the answer into the repository's data file.
    """
    monkeypatch.setattr("downloader.base.DEFAULT_REVERSE_GEOCODE_FILE", str(tmp_path / "reverse_geocode.csv"))
    monkeypatch.setattr("reverse_geocode.reverse_geocode", lambda *args, **kwargs: ("US", "MT"))
