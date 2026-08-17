from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kstock.domain.enums import Environment
from kstock.guard.risk_direction import classify_cancel_direction, classify_submit_direction
from kstock.policy.approval import validate_approval_context
from kstock.policy.model import (
    AccountStateSnapshot,
    ApprovalRiskBinding,
    AutomationLevel,
    KillSwitchState,
    OpenOrderState,
    OpenOrdersSnapshot,
    PositionState,
    QuoteSnapshot,
    RiskDirection,
)
from kstock.policy.odd import (
    direction_allowed_by_kill_switch,
    evaluate_normal_odd,
    evaluate_recovery_odd,
)
from kstock.policy.runtime_control import RuntimeControlStore
from kstock.watch.invalidation import ReevaluationRequest, evaluate_invalidation


def _now():
    return datetime.now(timezone.utc)


def _account(qty: int, *, available: bool = True, age: int = 0):
    now = _now()
    return AccountStateSnapshot(
        account_ref="PAPER_PRIMARY",
        positions=(PositionState("005930", qty),),
        as_of=now - timedelta(seconds=age),
        fetched_at=now - timedelta(seconds=age),
        available=available,
    )


def _orders(*orders: OpenOrderState, available: bool = True, age: int = 0):
    now = _now()
    return OpenOrdersSnapshot(
        account_ref="PAPER_PRIMARY",
        orders=tuple(orders),
        as_of=now - timedelta(seconds=age),
        fetched_at=now - timedelta(seconds=age),
        available=available,
    )


def _quote(*, age: int = 0, available: bool = True):
    now = _now()
    return QuoteSnapshot("005930", 80000, now - timedelta(seconds=age), now - timedelta(seconds=age), available)


def test_08_risk_direction_is_recomputed_from_latest_authoritative_state() -> None:
    old = classify_submit_direction(
        symbol="005930", side="SELL", quantity=30, account=_account(100), open_orders=_orders()
    )
    latest = classify_submit_direction(
        symbol="005930", side="SELL", quantity=30, account=_account(20), open_orders=_orders()
    )
    assert old.direction is RiskDirection.REDUCE
    assert latest.direction is RiskDirection.INCREASE


def test_09_changed_risk_direction_invalidates_existing_approval(paper_policy) -> None:
    account = _account(100)
    orders = _orders()
    approved_assessment = classify_submit_direction(
        symbol="005930", side="SELL", quantity=30, account=account, open_orders=orders
    )
    approval = ApprovalRiskBinding(
        approval_id="appr1",
        proposal_hash="proposal-hash",
        environment=Environment.PAPER,
        account_ref="PAPER_PRIMARY",
        approved_direction=approved_assessment.direction,
        approved_assessment_hash=approved_assessment.assessment_hash,
        approved_by="OWNER",
        approved_at=_now(),
    )
    latest = classify_submit_direction(
        symbol="005930", side="SELL", quantity=30, account=_account(20), open_orders=orders
    )
    ok, code = validate_approval_context(
        approval=approval,
        proposal_hash="proposal-hash",
        current_assessment=latest,
        bundle=paper_policy,
    )
    assert not ok
    assert code == "APPROVAL_RISK_DIRECTION_CHANGED"


def test_10_stale_account_or_quote_blocks_normal_odd_for_new_risk(paper_policy) -> None:
    result = evaluate_normal_odd(
        bundle=paper_policy,
        now=_now(),
        account=_account(0, age=60),
        open_orders=_orders(),
        quote=_quote(age=60),
        market="KR_EQUITY",
        product_type="COMMON_STOCK",
        session="REGULAR",
        order_type="LIMIT",
    )
    assert result.status.value == "OUT_OF_ODD"
    assert "ACCOUNT_STATE_STALE" in result.reasons
    assert "QUOTE_STALE" in result.reasons


def test_11_invalidation_creates_review_request_not_auto_sell() -> None:
    result = evaluate_invalidation(security_id="KRX:005930", thesis_id="th1", matched=True)
    assert isinstance(result, ReevaluationRequest)
    assert not hasattr(result, "quantity")
    assert not hasattr(result, "order_intent")


def test_12_no_new_risk_blocks_increase_but_recovery_can_review_reduce(paper_policy) -> None:
    assert not direction_allowed_by_kill_switch(KillSwitchState.NO_NEW_RISK, RiskDirection.INCREASE)
    assert direction_allowed_by_kill_switch(KillSwitchState.NO_NEW_RISK, RiskDirection.REDUCE)
    recovery = evaluate_recovery_odd(
        bundle=paper_policy,
        direction=RiskDirection.REDUCE,
        account=_account(100),
        open_orders=_orders(),
    )
    assert recovery.status.value == "IN_ODD"


def test_13_long_only_fresh_open_buy_can_use_cancel_only_recovery(paper_policy) -> None:
    target = OpenOrderState("ord-buy", "005930", "BUY", 10)
    account = _account(100, available=False)
    orders = _orders(target, available=True)
    assessment = classify_cancel_direction(target_order_id="ord-buy", account=account, open_orders=orders)
    assert assessment.direction is RiskDirection.REDUCE
    result = evaluate_recovery_odd(
        bundle=paper_policy,
        direction=assessment.direction,
        account=account,
        open_orders=orders,
        target_order_id="ord-buy",
    )
    assert result.status.value == "IN_ODD"
    assert "LONG_ONLY_CANCEL_BUY_FALLBACK" in result.reasons


def test_14_open_orders_unavailable_recommends_hard_frozen(paper_policy) -> None:
    result = evaluate_recovery_odd(
        bundle=paper_policy,
        direction=RiskDirection.REDUCE,
        account=_account(100),
        open_orders=_orders(available=False),
    )
    assert result.recommended_kill_switch is KillSwitchState.HARD_FROZEN
