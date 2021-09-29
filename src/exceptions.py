from __future__ import annotations


class ValidationError(Exception):
    def __init__(self, message: str | None) -> None:
        self.message = message
