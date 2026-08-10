from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class PortfolioVerdict:
    status: str
    code: str
