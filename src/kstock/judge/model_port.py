from __future__ import annotations

from typing import Protocol


class ModelPort(Protocol):
    def generate(self, prompt: str) -> object: ...
