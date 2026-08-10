from __future__ import annotations

"""Chapter 6 - broker/idempotency runtime contract."""

from dataclasses import dataclass

from kstock.broker.adapter import BrokerAdapter
from kstock.broker.idempotency import derive_submission_key


@dataclass
class _MaliciousIntent:
    """Duck-typed intent carrying a forged key that broker must ignore."""

    intent_id: str
    security_id: str
    side: str
    qty: int
    price: int
    submission_key: str


class _CapturingTransport:
    def __init__(self) -> None:
        self.last_request = None

    def submit(self, request):
        self.last_request = request
        return {"broker_order_id": "paper-001", "accepted": True}


# Scenario 19 - runtime half

def test_19_broker_derives_submission_key_from_intent_id_and_ignores_forged_key() -> None:
    transport = _CapturingTransport()
    adapter = BrokerAdapter(transport=transport)
    intent = _MaliciousIntent(
        intent_id="intent-001",
        security_id="KR7005930003",
        side="BUY",
        qty=10,
        price=80000,
        submission_key="FORGED-CALLER-KEY",
    )

    adapter.submit_order(intent)  # type: ignore[arg-type]

    assert transport.last_request is not None
    assert transport.last_request.submission_key == derive_submission_key(intent.intent_id)
    assert transport.last_request.submission_key != intent.submission_key
