from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kstock.fixed_identity import OWNER_ACTOR_ID
from kstock.guard.risk_direction import classify_submit_direction

from .approval import validate_approval_context
from .model import (
    AccountStateSnapshot,
    ApprovalRiskBinding,
    ExecutionPermit,
    KillSwitchState,
    OpenOrdersSnapshot,
    PermissionStatus,
    PolicyBundle,
    QuoteSnapshot,
    RiskDirection,
    RuntimeControlState,
)
from .odd import direction_allowed_by_kill_switch, evaluate_normal_odd, evaluate_recovery_odd
from .permissions import decide_permission
from .runtime_control import validate_execution_permit


@dataclass(frozen=True, slots=True)
class PreTradeResult:
    allowed: bool
    code: str
    direction: RiskDirection | None = None


def pretrade_submit_check(
    *,
    bundle: PolicyBundle,
    runtime: RuntimeControlState,
    permit: ExecutionPermit,
    proposal_hash: str,
    approval: ApprovalRiskBinding | None,
    symbol: str,
    side: str,
    quantity: int,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
    quote: QuoteSnapshot,
    now: datetime,
    product_type: str = "COMMON_STOCK",
    session: str = "REGULAR",
    order_type: str = "LIMIT",
    actor: str = "SERVICE",
) -> PreTradeResult:
    permit_ok, permit_code = validate_execution_permit(
        permit=permit,
        runtime=runtime,
        active_policy_version=bundle.policy_version,
    )
    if not permit_ok:
        return PreTradeResult(False, permit_code)

    permission = decide_permission(
        bundle=bundle,
        runtime=runtime,
        action_id="BROKER_SUBMIT",
        actor=actor,
        owner_approval_present=approval is not None and approval.approved_by == OWNER_ACTOR_ID,
    )
    if permission.status is PermissionStatus.BLOCKED:
        return PreTradeResult(False, permission.code)

    try:
        assessment = classify_submit_direction(
            symbol=symbol,
            side=side,
            quantity=quantity,
            account=account,
            open_orders=open_orders,
        )
    except ValueError:
        return PreTradeResult(False, "AUTHORITATIVE_STATE_UNAVAILABLE")

    if not direction_allowed_by_kill_switch(runtime.kill_switch_state, assessment.direction):
        return PreTradeResult(False, "KILL_SWITCH_BLOCKED_DIRECTION", assessment.direction)

    if runtime.kill_switch_state is KillSwitchState.NO_NEW_RISK:
        odd = evaluate_recovery_odd(
            bundle=bundle,
            direction=assessment.direction,
            account=account,
            open_orders=open_orders,
            now=now,
            quote=quote,
            new_order=True,
        )
    else:
        odd = evaluate_normal_odd(
            bundle=bundle,
            now=now,
            account=account,
            open_orders=open_orders,
            quote=quote,
            market="KR_EQUITY",
            product_type=product_type,
            session=session,
            order_type=order_type,
        )
    if odd.status.value != "IN_ODD":
        return PreTradeResult(False, "ODD_NOT_SATISFIED", assessment.direction)

    approval_ok, approval_code = validate_approval_context(
        approval=approval,
        proposal_hash=proposal_hash,
        current_assessment=assessment,
        bundle=bundle,
    )
    if not approval_ok:
        return PreTradeResult(False, approval_code, assessment.direction)

    return PreTradeResult(True, "PASS", assessment.direction)
