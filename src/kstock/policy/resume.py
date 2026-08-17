from __future__ import annotations

from kstock.fixed_identity import OWNER_ACTOR_ID

from .model import KillSwitchState, OddStatus
from .runtime_control import RuntimeControlStore


def resume_trading(
    *,
    store: RuntimeControlStore,
    owner_actor_id: str,
    confirmation: str,
    reason: str,
    odd_status: OddStatus,
    reconciliation_status: str,
    audit_healthy: bool,
    unknown_orders: int,
) -> tuple[bool, str]:
    if owner_actor_id != OWNER_ACTOR_ID:
        return False, "OWNER_REQUIRED"
    if confirmation != "RESUME TRADING":
        return False, "CONFIRMATION_MISMATCH"
    if not reason.strip():
        return False, "RESUME_REASON_REQUIRED"
    if odd_status is not OddStatus.IN_ODD:
        return False, "ODD_NOT_IN"
    if reconciliation_status != "MATCH":
        return False, "RECONCILIATION_NOT_MATCH"
    if not audit_healthy:
        return False, "AUDIT_UNHEALTHY"
    if unknown_orders != 0:
        return False, "UNKNOWN_ORDERS_REMAIN"
    store.set_odd_status(OddStatus.IN_ODD, reason="resume precheck")
    store.relax_kill_switch(KillSwitchState.NORMAL, actor_id=owner_actor_id, reason=reason)
    return True, "PASS"
