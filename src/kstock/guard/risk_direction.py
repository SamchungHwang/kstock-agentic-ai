from __future__ import annotations

from datetime import datetime, timezone

from kstock.policy.model import (
    AccountStateSnapshot,
    OpenOrdersSnapshot,
    RiskDirection,
    RiskDirectionAssessment,
    stable_hash,
)


class RiskDirectionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assessment(
    direction: RiskDirection,
    *,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
    reasons: tuple[str, ...],
) -> RiskDirectionAssessment:
    payload = {
        "direction": direction.value,
        "account_ref": account.account_ref,
        "account_as_of": account.as_of,
        "open_orders_as_of": open_orders.as_of,
        "positions": [(p.symbol, p.quantity) for p in account.positions],
        "open_orders": [(o.order_id, o.symbol, o.side, o.remaining_qty) for o in open_orders.orders],
        "reasons": reasons,
    }
    return RiskDirectionAssessment(
        direction=direction,
        assessment_hash=stable_hash(payload),
        assessed_at=_now(),
        account_as_of=account.as_of,
        open_orders_as_of=open_orders.as_of,
        reasons=reasons,
    )


def classify_submit_direction(
    *,
    symbol: str,
    side: str,
    quantity: int,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
) -> RiskDirectionAssessment:
    if not account.available or not open_orders.available:
        raise RiskDirectionError("authoritative account/open-order state unavailable")
    if account.account_ref != open_orders.account_ref:
        raise RiskDirectionError("account/open-order snapshot mismatch")
    if quantity <= 0:
        raise RiskDirectionError("quantity must be positive")

    side = side.upper()
    current_qty = account.quantity(symbol)
    if current_qty < 0:
        raise RiskDirectionError("LONG_ONLY ODD does not allow negative position")

    if side == "BUY":
        direction = RiskDirection.INCREASE
        reasons = ("BUY_INCREASES_LONG_EXPOSURE",)
    elif side == "SELL":
        if quantity < current_qty:
            direction = RiskDirection.REDUCE
            reasons = ("SELL_REDUCES_EXISTING_LONG",)
        elif quantity == current_qty and current_qty > 0:
            direction = RiskDirection.EXIT
            reasons = ("SELL_EXITS_EXISTING_LONG",)
        else:
            direction = RiskDirection.INCREASE
            reasons = ("SELL_WOULD_CROSS_BELOW_ZERO_OR_CREATE_SHORT",)
    else:
        raise RiskDirectionError(f"unsupported side: {side}")

    return _assessment(direction, account=account, open_orders=open_orders, reasons=reasons)


def classify_cancel_direction(
    *,
    target_order_id: str,
    account: AccountStateSnapshot,
    open_orders: OpenOrdersSnapshot,
) -> RiskDirectionAssessment:
    if not open_orders.available:
        raise RiskDirectionError("authoritative open-orders unavailable")
    if account.account_ref != open_orders.account_ref:
        raise RiskDirectionError("account/open-order snapshot mismatch")
    target = open_orders.find(target_order_id)
    if target is None or target.remaining_qty <= 0:
        raise RiskDirectionError("target open order unavailable")

    side = target.side.upper()
    if side == "BUY":
        # 이 책의 초기 ODD는 LONG_ONLY다. 미체결 BUY 제거는 새 롱 노출 가능성을 줄인다.
        direction = RiskDirection.REDUCE
        reasons = ("CANCEL_OPEN_BUY_REMOVES_POTENTIAL_LONG_EXPOSURE",)
    elif side == "SELL":
        # LONG_ONLY에서는 보유 축소/청산 주문을 취소하면 위험 축소 기회를 되돌린다.
        direction = RiskDirection.INCREASE
        reasons = ("CANCEL_OPEN_SELL_REMOVES_RISK_REDUCTION",)
    else:
        raise RiskDirectionError(f"unsupported target side: {side}")

    return _assessment(direction, account=account, open_orders=open_orders, reasons=reasons)
