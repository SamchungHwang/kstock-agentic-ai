from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .idempotency import derive_submission_key


class BrokerTransport(Protocol):
    def submit(self, request: object) -> object: ...


@dataclass(frozen=True, kw_only=True)
class BrokerRequest:
    intent_id: str
    security_id: str
    side: str
    qty: int
    price: int
    submission_key: str


class BrokerAdapter:
    def __init__(self, *, transport: BrokerTransport) -> None:
        self._transport = transport

    def submit_order(self, intent: object) -> object:
        intent_id = str(getattr(intent, "intent_id"))
        submission_key = derive_submission_key(intent_id)
        request = BrokerRequest(
            intent_id=intent_id,
            security_id=str(getattr(intent, "security_id")),
            side=str(getattr(intent, "side")),
            qty=int(getattr(intent, "qty")),
            price=int(getattr(intent, "price")),
            submission_key=submission_key,
        )
        return self._transport.submit(request)
