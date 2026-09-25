from __future__ import annotations

import logging
from typing import Any


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
