from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class BrokerOutcome:
    accepted: bool
    broker_order_id: str | None
    code: str
