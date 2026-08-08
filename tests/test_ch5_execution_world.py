from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kstock.execution_world import (
    Account,
    Actor,
    Approval,
    Authority,
    BrokerPositionSnapshot,
    ConfirmedThesisRef,
    ConstraintViolation,
    ContractValidationError,
    DraftThesisRef,
    Environment,
    Event,
    IllegalTransition,
    Issuer,
    KillSwitchState,
    MemoryContext,
    Observation,
    Order,
    OrderEvent,
    OrderState,
    Position,
    Proposal,
    ReconciliationState,
    Security,
    StateCoordinate,
    TraceRecord,
    TradingGateState,
    apply_order_event,
    assign_broker_order_id,
    authoritative_position_quantity,
    can_auto_resubmit,
    create_control_commit,
    create_economic_commit,
    ensure_snapshot_usable,
    make_approval,
    new_risk_blockers,
    reconcile_position,
    require_confirmed_thesis,
    resolve_submission_snapshot,
    trace_correlation,
    validate_execution_world_contract,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)


def snap(qty: int, *, fetched_at: datetime = T0) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_ref="KIS_CASH_MAIN",
        security_id="sec_005930",
        quantity=qty,
        as_of=T0,
        fetched_at=fetched_at,
    )


def order(state: OrderState = OrderState.CREATED, env: Environment = Environment.PAPER) -> Order:
    return Order(
        order_id="ord_1",
        intent_id="intent_1",
        account_ref="KIS_CASH_MAIN",
        security_id="sec_005930",
        environment=env,
        state=state,
    )


def test_01_context_is_memory_not_authoritative_position_state():
    ctx = MemoryContext({"sec_005930": 10})
    assert authoritative_position_quantity(context=ctx, broker_snapshot=snap(12)) == 12


def test_02_submission_uses_authority_snapshot_not_gui_copy():
    gui = snap(10, fetched_at=T0 - timedelta(minutes=20))
    auth = snap(12, fetched_at=T0)
    chosen = resolve_submission_snapshot(
        gui_snapshot=gui,
        authority_snapshot=auth,
        decision_time=T0 + timedelta(seconds=1),
    )
    assert chosen.quantity == 12


def test_03_issuer_and_security_are_distinct_entities():
    issuer = Issuer("issuer_samsung", "00126380", "삼성전자")
    common = Security("sec_common", issuer.issuer_id, "005930", "COMMON")
    preferred = Security("sec_pref", issuer.issuer_id, "005935", "PREFERRED")
    assert common.issuer_id == preferred.issuer_id == issuer.issuer_id
    assert common.security_id != preferred.security_id
    assert common.symbol != preferred.symbol


def test_04_draft_thesis_cannot_enter_portfolio_stage():
    with pytest.raises(ConstraintViolation, match="NO_DRAFT_TO_SIZING"):
        require_confirmed_thesis(DraftThesisRef("draft_1"))
    assert require_confirmed_thesis(ConfirmedThesisRef("thesis_1")).thesis_id == "thesis_1"


def test_05_approval_is_append_only_record_with_target_hash():
    proposal = {"proposal_id": "p1", "qty": 2, "hash": "hash_p1"}
    before = dict(proposal)
    approval = make_approval(
        approval_id="a1",
        target_id="p1",
        target_hash="hash_p1",
        approved_by="owner",
        decided_at=T0,
    )
    assert proposal == before
    assert approval.target_id == "p1"
    assert approval.target_hash == "hash_p1"


def test_06_created_cannot_receive_full_fill_directly():
    with pytest.raises(IllegalTransition):
        apply_order_event(order(), OrderEvent.FULL_FILL)


def test_07_submit_timeout_becomes_unknown_not_rejected():
    submitting = apply_order_event(order(), OrderEvent.SUBMIT_REQUESTED)
    timed_out = apply_order_event(submitting, OrderEvent.TIMEOUT)
    assert timed_out.state is OrderState.UNKNOWN


def test_08_unknown_order_has_no_auto_resubmit_path():
    assert can_auto_resubmit(order(OrderState.UNKNOWN)) is False


def test_09_kill_switch_blocks_new_risk_even_if_gate_open():
    blockers = new_risk_blockers(
        gate=TradingGateState.OPEN,
        kill_switch=KillSwitchState.ON,
        reconciliation=ReconciliationState.MATCH,
        audit_healthy=True,
    )
    assert "NO_NEW_RISK_WHEN_KILL_SWITCH_ON" in blockers


def test_10_reconciliation_unknown_is_not_match():
    blockers = new_risk_blockers(
        gate=TradingGateState.OPEN,
        kill_switch=KillSwitchState.OFF,
        reconciliation=ReconciliationState.UNKNOWN,
        audit_healthy=True,
    )
    assert "NO_NEW_RISK_WHEN_RECONCILIATION_NOT_MATCH" in blockers


def test_11_mismatch_does_not_overwrite_either_side():
    outcome = reconcile_position(ledger_qty=10, broker_qty=12)
    assert outcome.status is ReconciliationState.MISMATCH
    assert outcome.ledger_value == 10
    assert outcome.broker_value == 12
    assert outcome.recovery_required is True


def test_12_policy_version_is_part_of_execution_coordinate():
    base = dict(
        as_of=T0,
        fetched_at=T0,
        market="KRX",
        environment=Environment.PAPER,
        account_ref="KIS_CASH_MAIN",
        actor=Actor.WORKER,
        source="broker",
    )
    a = StateCoordinate(**base, policy_version="policy-v1")
    b = StateCoordinate(**base, policy_version="policy-v2")
    assert a != b


def test_13_paper_intent_cannot_be_promoted_to_live_implicitly():
    blockers = new_risk_blockers(
        gate=TradingGateState.OPEN,
        kill_switch=KillSwitchState.OFF,
        reconciliation=ReconciliationState.MATCH,
        audit_healthy=True,
        intent_environment=Environment.PAPER,
        execution_environment=Environment.LIVE,
    )
    assert "NO_IMPLICIT_PAPER_TO_LIVE_PROMOTION" in blockers


def test_14_observation_type_has_no_judge_conclusion_field():
    coord = StateCoordinate(
        as_of=T0,
        fetched_at=T0,
        market="KRX",
        environment=Environment.PAPER,
        account_ref="KIS_CASH_MAIN",
        actor=Actor.BROKER,
        source="quote",
        policy_version="v1",
    )
    with pytest.raises(TypeError):
        Observation(
            observation_id="obs1",
            subject_id="sec_005930",
            value=82400,
            coordinate=coord,
            conclusion="BUY",  # type: ignore[call-arg]
        )


def test_15_proposal_does_not_change_position_quantity():
    position = Position("KIS_CASH_MAIN", "sec_005930", 10, T0, T0)
    before = position
    _ = Proposal("proposal_1", "judgment_1", "sec_005930", "hash1")
    assert position == before
    assert position.quantity == 10


def test_16_broker_order_id_requires_broker_event():
    candidate = order(OrderState.SUBMITTING)
    fake = Event("evt1", "LOCAL_SUBMIT_SUCCESS", Authority.LEDGER, T0, "corr1", {})
    with pytest.raises(ConstraintViolation):
        assign_broker_order_id(candidate, event=fake, broker_order_id="12345")
    broker = Event("evt2", "BROKER_ACCEPTED", Authority.BROKER, T0, "corr1", {})
    accepted = assign_broker_order_id(candidate, event=broker, broker_order_id="12345")
    assert accepted.broker_order_id == "12345"


def test_17_correlation_trace_reconstructs_control_and_economic_sequence():
    kinds = [
        "APPROVAL",
        "INTENT_ISSUED",
        "SUBMIT_REQUESTED",
        "SUBMISSION_UNKNOWN",
        "BROKER_ORDER_FOUND",
        "FILL_RECEIVED",
        "RECONCILIATION_MATCH",
    ]
    records = [
        TraceRecord(i, "corr_x", kind, T0 + timedelta(seconds=i))
        for i, kind in enumerate(kinds, 1)
    ]
    records.append(TraceRecord(1, "other", "NOISE", T0))
    trace = trace_correlation(records, "corr_x")
    assert [r.kind for r in trace] == kinds


def test_18_audit_failure_blocks_risk_increasing_control_commit():
    with pytest.raises(ConstraintViolation, match="AUDIT_UNHEALTHY"):
        create_control_commit(
            commit_id="cc1",
            kind="GATE_OPEN",
            actor=Actor.OWNER,
            correlation_id="corr1",
            audit_healthy=False,
            committed_at=T0,
        )


def test_19_snapshot_requires_time_coordinates_and_rejects_future_fetch():
    good = snap(12, fetched_at=T0)
    ensure_snapshot_usable(good, T0 + timedelta(seconds=1))
    future = snap(12, fetched_at=T0 + timedelta(minutes=1))
    with pytest.raises(ConstraintViolation, match="future fetched_at"):
        ensure_snapshot_usable(future, T0)


def test_20_forbidden_transition_added_to_config_fails_contract(project_root: Path):
    path = project_root / "config" / "domain" / "execution_world.yaml"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["transitions"]["order"]["CREATED"]["FULL_FILL"] = "FILLED"
    with pytest.raises(ContractValidationError):
        validate_execution_world_contract(config)
