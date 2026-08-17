from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from kstock.policy.model import OddStatus, RiskDirection, stable_hash


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PolicyAuditEvent:
    event_id: str
    event_type: str
    occurred_at: datetime
    actor: str
    environment: str
    account_ref: str
    policy_version: str
    control_version: int
    risk_direction: RiskDirection | None
    odd_status: OddStatus | None
    reason_code: str
    correlation_id: str
    payload: dict[str, Any]
    event_hash: str


def make_policy_audit_event(
    *,
    event_type: str,
    actor: str,
    environment: str,
    account_ref: str,
    policy_version: str,
    control_version: int,
    risk_direction: RiskDirection | None,
    odd_status: OddStatus | None,
    reason_code: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
) -> PolicyAuditEvent:
    base = {
        "event_id": f"audit7_{uuid4().hex[:12]}",
        "event_type": event_type,
        "occurred_at": utcnow(),
        "actor": actor,
        "environment": environment,
        "account_ref": account_ref,
        "policy_version": policy_version,
        "control_version": int(control_version),
        "risk_direction": risk_direction.value if risk_direction else None,
        "odd_status": odd_status.value if odd_status else None,
        "reason_code": reason_code,
        "correlation_id": correlation_id,
        "payload": payload or {},
    }
    event_hash = stable_hash(base)
    return PolicyAuditEvent(
        event_id=base["event_id"],
        event_type=event_type,
        occurred_at=base["occurred_at"],
        actor=actor,
        environment=environment,
        account_ref=account_ref,
        policy_version=policy_version,
        control_version=int(control_version),
        risk_direction=risk_direction,
        odd_status=odd_status,
        reason_code=reason_code,
        correlation_id=correlation_id,
        payload=payload or {},
        event_hash=event_hash,
    )


def event_to_dict(event: PolicyAuditEvent) -> dict[str, Any]:
    value = asdict(event)
    value["occurred_at"] = event.occurred_at.isoformat()
    value["risk_direction"] = event.risk_direction.value if event.risk_direction else None
    value["odd_status"] = event.odd_status.value if event.odd_status else None
    return value
