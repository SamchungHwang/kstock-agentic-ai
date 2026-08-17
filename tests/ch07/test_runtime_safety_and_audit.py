from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from kstock.audit.policy_events import make_policy_audit_event
from kstock.audit.promotion_evidence import PromotionEvidenceBuilder
from kstock.domain.enums import Environment
from kstock.policy.model import (
    AutomationLevel,
    KillSwitchState,
    OddStatus,
    RiskDirection,
)
from kstock.policy.resume import resume_trading
from kstock.policy.runtime_control import (
    RuntimeControlStore,
    issue_execution_permit,
    validate_execution_permit,
)
from kstock.safety.kernel import SafetyKernel, SafetyKernelForbidden


def test_15_safety_kernel_escalates_even_without_policy_bundle() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    kernel = SafetyKernel(store)
    state = kernel.escalate(KillSwitchState.NO_NEW_RISK, reason="POLICY_LOAD_FAILED")
    assert state.kill_switch_state is KillSwitchState.NO_NEW_RISK
    assert state.control_version == 1


def test_16_safety_kernel_cannot_relax_submit_cancel_or_promote() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    kernel = SafetyKernel(store)
    forbidden_calls = [
        lambda: kernel.escalate(KillSwitchState.NORMAL, reason="bad"),
        kernel.deactivate,
        kernel.attempt_submission,
        kernel.attempt_cancel,
        kernel.promote_automation,
    ]
    for call in forbidden_calls:
        with pytest.raises(SafetyKernelForbidden):
            call()


def test_17_kill_switch_and_automation_changes_increment_control_version() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A2)
    assert store.read().control_version == 0
    store.escalate_kill_switch(KillSwitchState.NO_NEW_RISK, reason="test")
    assert store.read().control_version == 1
    store.demote_automation(AutomationLevel.A1)
    assert store.read().control_version == 2


def test_18_quote_refresh_does_not_increment_control_version() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    before = store.read().control_version
    store.note_quote_refresh()
    assert store.read().control_version == before


def test_19_execution_permit_fails_when_control_version_changed() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    permit = issue_execution_permit(
        permit_id="permit1",
        intent_id="intent1",
        policy_version="policy-1",
        runtime=store.read(),
    )
    store.escalate_kill_switch(KillSwitchState.NO_NEW_RISK, reason="halt")
    ok, code = validate_execution_permit(
        permit=permit,
        runtime=store.read(),
        active_policy_version="policy-1",
    )
    assert not ok
    assert code == "CONTROL_VERSION_CHANGED_RECHECK_REQUIRED"


def test_20_resume_rechecks_current_state_and_owner_confirmation() -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    store.set_odd_status(OddStatus.IN_ODD, reason="normal odd restored")
    store.escalate_kill_switch(KillSwitchState.NO_NEW_RISK, reason="temporary halt")
    before = store.read().control_version
    ok, code = resume_trading(
        store=store,
        owner_actor_id="OWNER",
        confirmation="RESUME TRADING",
        reason="대사 및 ODD 재확인 완료",
        odd_status=OddStatus.IN_ODD,
        reconciliation_status="MATCH",
        audit_healthy=True,
        unknown_orders=0,
    )
    assert ok and code == "PASS"
    assert store.read().kill_switch_state is KillSwitchState.NORMAL
    assert store.read().control_version > before

    bad, bad_code = resume_trading(
        store=store,
        owner_actor_id="OWNER",
        confirmation="RESUME TRADING",
        reason="test",
        odd_status=OddStatus.OUT_OF_ODD,
        reconciliation_status="MATCH",
        audit_healthy=True,
        unknown_orders=0,
    )
    assert not bad and bad_code == "ODD_NOT_IN"


def _event(kind: str):
    return make_policy_audit_event(
        event_type=kind,
        actor="OWNER",
        environment="PAPER",
        account_ref="PAPER_PRIMARY",
        policy_version="2026-08-16.paper.1",
        control_version=3,
        risk_direction=RiskDirection.INCREASE,
        odd_status=OddStatus.IN_ODD,
        reason_code="TEST",
        correlation_id="corr-test",
    )


def test_21_promotion_evidence_is_derived_from_audit_events_not_manual_counts() -> None:
    builder = PromotionEvidenceBuilder()
    assert list(inspect.signature(builder.build).parameters) == ["events"]
    evidence = builder.build([
        _event("PAPER_CASE_COMPLETED"),
        _event("PAPER_CASE_COMPLETED"),
        _event("SHADOW_CASE_COMPLETED"),
        _event("EXPECTED_BLOCK"),
    ])
    assert evidence.paper_cases == 2
    assert evidence.shadow_cases == 1
    assert evidence.blocked_cases == 1
    assert evidence.source_event_count == 4


def test_22_policy_audit_contains_required_chapter7_fields() -> None:
    event = _event("GUARD_DECISION")
    assert event.policy_version
    assert event.actor == "OWNER"
    assert event.risk_direction is RiskDirection.INCREASE
    assert event.odd_status is OddStatus.IN_ODD
    assert event.control_version == 3
    assert event.reason_code == "TEST"
