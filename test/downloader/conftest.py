from __future__ import annotations


class MockLogger:
    """Shared test logger that records messages for assertion."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, msg: str) -> None:
        self.messages.append(("INFO", msg))

    def error(self, msg: str) -> None:
        self.messages.append(("ERROR", msg))

    def warning(self, msg: str) -> None:
        self.messages.append(("WARNING", msg))
