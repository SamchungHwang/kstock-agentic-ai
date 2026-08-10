from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ModelRef:
    provider: str
    name: str
    version: str
