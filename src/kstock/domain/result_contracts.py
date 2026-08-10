from __future__ import annotations

from dataclasses import dataclass

from .contracts import Contract


@dataclass(frozen=True, kw_only=True)
class ResultContract(Contract):
    status: str
    code: str
