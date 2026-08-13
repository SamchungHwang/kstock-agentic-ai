from __future__ import annotations

"""Chapter 6 - runtime/data contract tests.

This file intentionally fixes a small public API for Chapters 6+.
If production names differ, adapt imports once and keep the test invariants.
"""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from kstock.domain.actors import Actor, ActorRole, ActorType
from kstock.domain.enums import (
    Environment,
    GuardCode,
    GuardStatus,
    RecoveryClass,
    RiskDirection,
    ThesisStatus,
)
from kstock.domain.thesis_lifecycle import (
    ThesisLifecycleState,
    invalidate_thesis,
    supersede_thesis,
)
from kstock.guard.authorization import AuthorizationPolicy
from kstock.guard.decision import GuardInput, evaluate_guard
from kstock.guard.reasons import recovery_class_for
from kstock.judge.boundary import BoundaryContext, cross_boundary
from kstock.judge.drafts import InvestmentThesisDraft, PredicateDraft
from kstock.portfolio.proposal import build_proposal
from kstock.portfolio.sizing import PortfolioSnapshot, size_position


NOW = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)


def _boundary_context() -> BoundaryContext:
    return BoundaryContext(
        as_of=NOW,
        actor_id="judge-service",
        environment=Environment.PAPER,
        correlation_id="corr-ch6",
        policy_version="p-2026-08-10",
        model_provider="openai",
        model_name="gpt-5.6-sol",
        model_version="2026-08-10",
    )


def _structured_draft() -> InvestmentThesisDraft:
    return InvestmentThesisDraft(
        security_id="KR7005930003",
        thesis_text="메모리 업황과 HBM 출하 증가를 핵심 근거로 관찰한다.",
        conviction=Decimal("0.70"),
        invalidation_predicate=PredicateDraft(
            field="forward_eps_growth_pct",
            operator="LT",
            threshold=Decimal("0"),
            unit="pct",
            window="2Q",
        ),
        invalidation_text=None,
        evidence_ids=("ev-1", "ev-2"),
    )


def _issued_thesis():
    result = cross_boundary(_structured_draft(), _boundary_context())
    assert result.status == "PASS", result
    assert result.thesis is not None
    return result.thesis


def _active_lifecycle(thesis_id: str) -> ThesisLifecycleState:
    return ThesisLifecycleState(
        thesis_id=thesis_id,
        status=ThesisStatus.ACTIVE,
        changed_at=NOW,
        reason_code="ISSUED",
        superseded_by=None,
    )


# Scenario 3

def test_03_portfolio_rejects_unissued_investment_thesis_draft() -> None:
    draft = _structured_draft()
    snapshot = PortfolioSnapshot(
        nav=Decimal("100000000"),
        cash=Decimal("50000000"),
        current_exposure=Decimal("0"),
    )

    with pytest.raises(TypeError, match="InvestmentThesis"):
        size_position(
            thesis=draft,  # type: ignore[arg-type]
            lifecycle=_active_lifecycle("not-issued"),
            snapshot=snapshot,
            policy={"max_position_weight": "0.10"},
        )


# Scenario 5

def test_05_free_text_invalidation_without_predicate_blocks_thesis_issuance() -> None:
    draft = replace(
        _structured_draft(),
        invalidation_predicate=None,
        invalidation_text="실적이 크게 나빠지면 투자 논리를 무효화한다.",
    )

    result = cross_boundary(draft, _boundary_context())

    assert result.status == "BLOCKED"
    assert result.code == "INVALIDATION_PREDICATE_REQUIRED"
    assert result.thesis is None


# Scenario 6

def test_06_boundary_does_not_infer_numeric_predicate_from_natural_language() -> None:
    draft = replace(
        _structured_draft(),
        invalidation_predicate=None,
        invalidation_text="향후 EPS가 10% 이상 감소하면 무효화한다.",
    )

    result = cross_boundary(draft, _boundary_context())

    # The '10%' in free text must never be silently converted into a predicate.
    assert result.status == "BLOCKED"
    assert result.code == "INVALIDATION_PREDICATE_REQUIRED"
    assert result.thesis is None


# Scenario 7

def test_07_same_active_thesis_and_policy_produce_same_sizing_hash() -> None:
    thesis = _issued_thesis()
    lifecycle = _active_lifecycle(thesis.contract_id)
    snapshot = PortfolioSnapshot(
        nav=Decimal("100000000"),
        cash=Decimal("50000000"),
        current_exposure=Decimal("0.02"),
    )
    policy = {
        "max_position_weight": "0.10",
        "conviction_multiplier": "1.00",
        "min_cash_buffer": "0.20",
    }

    first = size_position(thesis=thesis, lifecycle=lifecycle, snapshot=snapshot, policy=policy)
    second = size_position(thesis=thesis, lifecycle=lifecycle, snapshot=snapshot, policy=deepcopy(policy))

    assert first.decision_hash == second.decision_hash
    assert first.target_weight == second.target_weight


# Scenario 8

def test_08_invalidated_thesis_cannot_create_risk_increase_proposal() -> None:
    thesis = _issued_thesis()
    lifecycle = invalidate_thesis(
        _active_lifecycle(thesis.contract_id),
        changed_at=NOW,
        reason_code="PREDICATE_MATCHED",
    )

    result = build_proposal(
        thesis=thesis,
        lifecycle=lifecycle,
        risk_direction=RiskDirection.INCREASE,
        target_weight=Decimal("0.08"),
    )

    assert result.status == "BLOCKED"
    assert result.code == "THESIS_NOT_ACTIVE"
    assert result.proposal is None


# Scenario 9
@pytest.mark.parametrize("direction", [RiskDirection.REDUCE, RiskDirection.EXIT])
def test_09_invalidated_thesis_is_usable_for_risk_reduction_review(direction: RiskDirection) -> None:
    thesis = _issued_thesis()
    lifecycle = invalidate_thesis(
        _active_lifecycle(thesis.contract_id),
        changed_at=NOW,
        reason_code="PREDICATE_MATCHED",
    )

    result = build_proposal(
        thesis=thesis,
        lifecycle=lifecycle,
        risk_direction=direction,
        target_weight=Decimal("0") if direction is RiskDirection.EXIT else Decimal("0.01"),
    )

    assert result.status == "PASS"
    assert result.proposal is not None
    assert result.proposal.risk_direction is direction


# Scenario 10

def test_10_new_thesis_supersedes_lifecycle_without_mutating_old_thesis_text() -> None:
    old_thesis = _issued_thesis()
    old_payload_before = asdict(old_thesis)
    old_lifecycle = _active_lifecycle(old_thesis.contract_id)

    new_result = cross_boundary(
        replace(_structured_draft(), thesis_text="새 근거로 재평가된 투자 논리다."),
        replace(_boundary_context(), correlation_id="corr-ch6-new"),
    )
    assert new_result.status == "PASS"
    new_thesis = new_result.thesis
    assert new_thesis is not None

    new_lifecycle = supersede_thesis(
        old_lifecycle,
        replacement_thesis_id=new_thesis.contract_id,
        changed_at=NOW,
    )

    assert asdict(old_thesis) == old_payload_before
    assert new_lifecycle.status is ThesisStatus.SUPERSEDED
    assert new_lifecycle.thesis_id == old_thesis.contract_id
    assert new_lifecycle.superseded_by == new_thesis.contract_id


# Scenario 11

def test_11_guard_final_status_domain_is_closed_to_pass_or_blocked() -> None:
    assert {item.value for item in GuardStatus} == {"PASS", "BLOCKED"}


class _StateProvider:
    def __init__(self, state=None, exc: Exception | None = None):
        self.state = state
        self.exc = exc

    def load_authoritative_state(self, security_id: str):
        if self.exc is not None:
            raise self.exc
        return self.state


def _human(actor_id: str = "OWNER", *, authenticated: bool = True, roles=None) -> Actor:
    return Actor(
        actor_id=actor_id,
        actor_type=ActorType.HUMAN,
        authenticated=authenticated,
        roles=frozenset(roles or {ActorRole.OWNER}),
    )


def _service(actor_id: str = "svc-1", *, authenticated: bool = True, roles=None) -> Actor:
    return Actor(
        actor_id=actor_id,
        actor_type=ActorType.SERVICE,
        authenticated=authenticated,
        roles=frozenset(roles or {ActorRole.SERVICE}),
    )


def _guard_input(*, actor: Actor, approved_by: Actor | None = None, command: str = "SUBMIT_ORDER") -> GuardInput:
    return GuardInput(
        command=command,
        security_id="KR7005930003",
        actor=actor,
        approved_by=approved_by,
        intent_id="intent-001",
    )


def _policy() -> AuthorizationPolicy:
    return AuthorizationPolicy(
        command_roles={
            "SUBMIT_ORDER": frozenset({ActorRole.OWNER, ActorRole.SERVICE}),
            "APPROVE_ORDER": frozenset({ActorRole.OWNER}),
            "EMERGENCY_HALT": frozenset({ActorRole.OWNER}),
        },
        human_only_commands=frozenset({"APPROVE_ORDER", "EMERGENCY_HALT"}),
        owner_approval_commands=frozenset({"SUBMIT_ORDER"}),
    )


# Scenario 12
@pytest.mark.parametrize(
    "provider",
    [
        _StateProvider(state=None),
        _StateProvider(exc=TimeoutError("authoritative state timeout")),
    ],
)
def test_12_authoritative_state_failure_is_fail_closed(provider: _StateProvider) -> None:
    decision = evaluate_guard(
        _guard_input(actor=_human()),
        state_provider=provider,
        authorization_policy=_policy(),
    )

    assert decision.status is GuardStatus.BLOCKED
    assert decision.code is GuardCode.STATE_UNAVAILABLE


# Scenario 13

def test_13_unauthenticated_actor_is_blocked() -> None:
    decision = evaluate_guard(
        _guard_input(actor=_human(authenticated=False)),
        state_provider=_StateProvider(state={"market_open": True}),
        authorization_policy=_policy(),
    )

    assert decision.status is GuardStatus.BLOCKED
    assert decision.code is GuardCode.ACTOR_UNAUTHENTICATED


# Scenario 14

def test_14_service_actor_cannot_invoke_human_only_command() -> None:
    decision = evaluate_guard(
        _guard_input(actor=_service(), command="EMERGENCY_HALT"),
        state_provider=_StateProvider(state={"market_open": True}),
        authorization_policy=_policy(),
    )

    assert decision.status is GuardStatus.BLOCKED
    assert decision.code is GuardCode.ACTOR_ROLE_FORBIDDEN


# Scenario 15

def test_15_owner_approval_may_be_executed_by_authorized_service() -> None:
    owner = _human()
    submitter = _service("order-worker")

    decision = evaluate_guard(
        _guard_input(actor=submitter, approved_by=owner, command="SUBMIT_ORDER"),
        state_provider=_StateProvider(state={"market_open": True}),
        authorization_policy=_policy(),
    )

    assert decision.status is GuardStatus.PASS
    assert decision.code is GuardCode.PASS
    assert owner.actor_id == "OWNER"
    assert submitter.actor_type is ActorType.SERVICE


def test_15b_second_human_identity_is_not_allowed() -> None:
    other_human = _human("OTHER_HUMAN")
    decision = evaluate_guard(
        _guard_input(actor=other_human, command="EMERGENCY_HALT"),
        state_provider=_StateProvider(state={"market_open": True}),
        authorization_policy=_policy(),
    )
    assert decision.status is GuardStatus.BLOCKED
    assert decision.code is GuardCode.ACTOR_ROLE_FORBIDDEN


# Scenario 16

def test_16_unknown_guard_code_defaults_to_human_required() -> None:
    mapping = {
        GuardCode.STATE_UNAVAILABLE.value: RecoveryClass.RETRYABLE,
        GuardCode.ACTOR_UNAUTHENTICATED.value: RecoveryClass.HUMAN_REQUIRED,
    }

    recovery = recovery_class_for("NEW_UNMAPPED_GUARD_CODE", mapping)

    assert recovery is RecoveryClass.HUMAN_REQUIRED

# Named data-contract test from Chapter 6 deliverable 3.
def test_judge_evidence_has_no_performance_labels() -> None:
    """Evidence presented to Judge must not contain future/performance labels."""
    from dataclasses import fields

    from kstock.watch.evidence import EvidencePacket

    field_names = {field.name.lower() for field in fields(EvidencePacket)}
    forbidden_exact = {
        "label",
        "target",
        "outcome",
        "future_return",
        "forward_return",
        "realized_return",
        "pnl",
        "realized_pnl",
        "alpha",
    }
    forbidden_fragments = ("future_return", "forward_return", "realized_pnl")

    assert field_names.isdisjoint(forbidden_exact), (
        "EvidencePacket leaks performance labels into Judge: "
        f"{sorted(field_names & forbidden_exact)}"
    )
    assert not any(fragment in name for name in field_names for fragment in forbidden_fragments)


def test_invalidated_thesis_cannot_increase_risk() -> None:
    """Alias of scenario 8 using the deliverable's named test contract."""
    thesis = _issued_thesis()
    lifecycle = invalidate_thesis(
        _active_lifecycle(thesis.contract_id),
        changed_at=NOW,
        reason_code="PREDICATE_MATCHED",
    )

    result = build_proposal(
        thesis=thesis,
        lifecycle=lifecycle,
        risk_direction=RiskDirection.INCREASE,
        target_weight=Decimal("0.08"),
    )

    assert result.status == "BLOCKED"
    assert result.code == "THESIS_NOT_ACTIVE"


def test_guard_is_fail_closed() -> None:
    """Any failure to establish authoritative state must end BLOCKED, never UNKNOWN/PASS."""
    decision = evaluate_guard(
        _guard_input(actor=_human()),
        state_provider=_StateProvider(exc=ConnectionError("state store unavailable")),
        authorization_policy=_policy(),
    )

    assert decision.status is GuardStatus.BLOCKED
    assert decision.code is GuardCode.STATE_UNAVAILABLE


def test_recovery_mapping_has_safe_default() -> None:
    assert recovery_class_for("UNMAPPED", {}) is RecoveryClass.HUMAN_REQUIRED
