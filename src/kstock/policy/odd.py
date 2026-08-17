from __future__ import annotations

from datetime import datetime

from .model import (
    AccountStateSnapshot,
    KillSwitchState,
    OddResult,
    OddStatus,
    OpenOrdersSnapshot,
    PolicyBundle,
    QuoteSnapshot,
    RiskDirection,
)


def _age_seconds(now: datetime, fetched_at: datetime) -> float:
    return max(0.0, (now - fetched_at).total_seconds())


def evaluate_normal_odd(
    *,
    bundle: PolicyBundle,
    now: datetime,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
    quote: QuoteSnapshot,
    market: str,
    product_type: str,
    session: str,
    order_type: str,
) -> OddResult:
    reasons: list[str] = []
    policy = bundle.odd
    if account.account_ref != bundle.account_ref or open_orders.account_ref != bundle.account_ref:
        reasons.append("ACCOUNT_BINDING_MISMATCH")
    if market not in {policy.market}:
        reasons.append("MARKET_NOT_ALLOWED")
    if product_type not in policy.products:
        reasons.append("PRODUCT_NOT_ALLOWED")
    if session not in policy.sessions:
        reasons.append("SESSION_NOT_ALLOWED")
    if order_type not in policy.order_types:
        reasons.append("ORDER_TYPE_NOT_ALLOWED")
    if not account.available:
        reasons.append("ACCOUNT_STATE_UNAVAILABLE")
    elif _age_seconds(now, account.fetched_at) > policy.account_max_age_seconds:
        reasons.append("ACCOUNT_STATE_STALE")
    if not open_orders.available:
        reasons.append("OPEN_ORDERS_UNAVAILABLE")
    elif _age_seconds(now, open_orders.fetched_at) > policy.open_orders_max_age_seconds:
        reasons.append("OPEN_ORDERS_STALE")
    if not quote.available:
        reasons.append("QUOTE_UNAVAILABLE")
    elif _age_seconds(now, quote.fetched_at) > policy.quote_max_age_seconds:
        reasons.append("QUOTE_STALE")
    if reasons:
        recommended = (
            KillSwitchState.HARD_FROZEN
            if "OPEN_ORDERS_UNAVAILABLE" in reasons
            else KillSwitchState.NO_NEW_RISK
        )
        return OddResult(OddStatus.OUT_OF_ODD, tuple(reasons), recommended)
    return OddResult(OddStatus.IN_ODD, (), None)


def evaluate_recovery_odd(
    *,
    bundle: PolicyBundle,
    direction: RiskDirection,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
    target_order_id: str | None = None,
    now: datetime | None = None,
    quote: QuoteSnapshot | None = None,
    new_order: bool = False,
) -> OddResult:
    policy = bundle.odd
    current_time = now or datetime.now(account.fetched_at.tzinfo)
    if direction is RiskDirection.INCREASE:
        return OddResult(OddStatus.OUT_OF_ODD, ("RECOVERY_CANNOT_INCREASE_RISK",), KillSwitchState.NO_NEW_RISK)
    if not open_orders.available:
        return OddResult(OddStatus.OUT_OF_ODD, ("OPEN_ORDERS_UNAVAILABLE",), KillSwitchState.HARD_FROZEN)
    if _age_seconds(current_time, open_orders.fetched_at) > policy.open_orders_max_age_seconds:
        return OddResult(OddStatus.OUT_OF_ODD, ("OPEN_ORDERS_STALE",), KillSwitchState.HARD_FROZEN)

    account_fresh = account.available and _age_seconds(current_time, account.fetched_at) <= policy.account_max_age_seconds
    if account_fresh and direction in {RiskDirection.REDUCE, RiskDirection.EXIT, RiskDirection.NEUTRAL}:
        if new_order:
            if quote is None or not quote.available:
                return OddResult(OddStatus.OUT_OF_ODD, ("QUOTE_UNAVAILABLE",), KillSwitchState.NO_NEW_RISK)
            if _age_seconds(current_time, quote.fetched_at) > policy.quote_max_age_seconds:
                return OddResult(OddStatus.OUT_OF_ODD, ("QUOTE_STALE",), KillSwitchState.NO_NEW_RISK)
        return OddResult(OddStatus.IN_ODD, (), None)

    # 제한적 cancel-only fallback: LONG_ONLY + fresh target BUY open order.
    if target_order_id and policy.long_only and not policy.short_sell_enabled and not policy.derivatives_enabled:
        target = open_orders.find(target_order_id)
        if target is not None and target.side.upper() == "BUY" and target.remaining_qty > 0:
            return OddResult(OddStatus.IN_ODD, ("LONG_ONLY_CANCEL_BUY_FALLBACK",), None)

    return OddResult(OddStatus.OUT_OF_ODD, ("RECOVERY_STATE_INSUFFICIENT",), KillSwitchState.HARD_FROZEN)


def direction_allowed_by_kill_switch(state: KillSwitchState, direction: RiskDirection) -> bool:
    if state is KillSwitchState.HARD_FROZEN:
        return False
    if state is KillSwitchState.NO_NEW_RISK:
        return direction in {RiskDirection.NEUTRAL, RiskDirection.REDUCE, RiskDirection.EXIT}
    return True
