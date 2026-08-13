from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from .fixed_identity import assert_fixed_account_binding, fixed_account_ref


class ExecutionWorldError(ValueError):
    pass


class IllegalTransition(ExecutionWorldError):
    pass


class ConstraintViolation(ExecutionWorldError):
    pass


class ContractValidationError(ExecutionWorldError):
    pass


class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class TradingGateState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


class KillSwitchState(str, Enum):
    OFF = "OFF"
    ON = "ON"


class ReconciliationState(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class OrderEvent(str, Enum):
    SUBMIT_REQUESTED = "SUBMIT_REQUESTED"
    BROKER_ACCEPTED = "BROKER_ACCEPTED"
    BROKER_REJECTED = "BROKER_REJECTED"
    TIMEOUT = "TIMEOUT"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    CANCEL_ACCEPTED = "CANCEL_ACCEPTED"
    BROKER_FOUND_SUBMITTED = "BROKER_FOUND_SUBMITTED"
    BROKER_FOUND_PARTIAL = "BROKER_FOUND_PARTIAL"
    BROKER_FOUND_FILLED = "BROKER_FOUND_FILLED"
    BROKER_FOUND_CANCELED = "BROKER_FOUND_CANCELED"
    BROKER_FOUND_REJECTED = "BROKER_FOUND_REJECTED"


class Authority(str, Enum):
    BROKER = "BROKER"
    LEDGER = "LEDGER"
    POLICY_BUNDLE = "POLICY_BUNDLE"
    AUDIT = "AUDIT"


class Actor(str, Enum):
    BROKER = "BROKER"
    OWNER = "OWNER"
    WORKER = "WORKER"
    JUDGE = "JUDGE"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class Issuer:
    issuer_id: str
    corp_code: str
    name: str


@dataclass(frozen=True)
class Security:
    security_id: str
    issuer_id: str
    symbol: str
    security_type: str


@dataclass(frozen=True)
class Account:
    account_ref: str
    environment: Environment

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True)
class Position:
    account_ref: str
    security_id: str
    quantity: int
    as_of: datetime
    fetched_at: datetime


@dataclass(frozen=True)
class InvestmentThesisEntity:
    thesis_id: str
    subject_id: str
    thesis_hash: str


@dataclass(frozen=True)
class Order:
    order_id: str
    intent_id: str
    account_ref: str
    security_id: str
    environment: Environment
    state: OrderState = OrderState.CREATED
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True)
class Approval:
    approval_id: str
    target_id: str
    target_hash: str
    approved_by: str
    decided_at: datetime


@dataclass(frozen=True)
class MemoryContext:
    """LLM/세션 기억. 권위 상태가 아니므로 경제 계산의 입력으로 쓰지 않는다."""

    remembered_position_qty: Mapping[str, int]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    account_ref: str
    security_id: str
    quantity: int
    as_of: datetime
    fetched_at: datetime


@dataclass(frozen=True)
class StateCoordinate:
    as_of: datetime
    fetched_at: datetime
    market: str
    environment: Environment
    account_ref: str
    actor: Actor
    source: str
    policy_version: str

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    subject_id: str
    value: Any
    coordinate: StateCoordinate


@dataclass(frozen=True)
class Judgment:
    judgment_id: str
    observation_ids: tuple[str, ...]
    conclusion: str
    produced_by: str


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    judgment_id: str
    target_id: str
    payload_hash: str


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    source: Authority
    occurred_at: datetime
    correlation_id: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ControlCommit:
    commit_id: str
    kind: str
    actor: Actor
    committed_at: datetime
    correlation_id: str


@dataclass(frozen=True)
class EconomicCommit:
    commit_id: str
    event_id: str
    economic_kind: str
    committed_at: datetime
    correlation_id: str


@dataclass(frozen=True)
class ReconciliationOutcome:
    status: ReconciliationState
    ledger_value: Any
    broker_value: Any
    recovery_required: bool


@dataclass(frozen=True)
class TraceRecord:
    sequence: int
    correlation_id: str
    kind: str
    at: datetime
    detail: str = ""


@dataclass(frozen=True)
class ConfirmedThesisRef:
    thesis_id: str


@dataclass(frozen=True)
class DraftThesisRef:
    draft_id: str


ORDER_TRANSITIONS: dict[OrderState, dict[OrderEvent, OrderState]] = {
    OrderState.CREATED: {
        OrderEvent.SUBMIT_REQUESTED: OrderState.SUBMITTING,
    },
    OrderState.SUBMITTING: {
        OrderEvent.BROKER_ACCEPTED: OrderState.SUBMITTED,
        OrderEvent.BROKER_REJECTED: OrderState.REJECTED,
        OrderEvent.TIMEOUT: OrderState.UNKNOWN,
    },
    OrderState.SUBMITTED: {
        OrderEvent.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEvent.FULL_FILL: OrderState.FILLED,
        OrderEvent.CANCEL_ACCEPTED: OrderState.CANCELED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderEvent.FULL_FILL: OrderState.FILLED,
        OrderEvent.CANCEL_ACCEPTED: OrderState.CANCELED,
    },
    OrderState.UNKNOWN: {
        OrderEvent.BROKER_FOUND_SUBMITTED: OrderState.SUBMITTED,
        OrderEvent.BROKER_FOUND_PARTIAL: OrderState.PARTIALLY_FILLED,
        OrderEvent.BROKER_FOUND_FILLED: OrderState.FILLED,
        OrderEvent.BROKER_FOUND_CANCELED: OrderState.CANCELED,
        OrderEvent.BROKER_FOUND_REJECTED: OrderState.REJECTED,
    },
}


AUTHORITY_BY_FACT: dict[str, Authority] = {
    "cash": Authority.BROKER,
    "holdings": Authority.BROKER,
    "broker_order": Authority.BROKER,
    "fill": Authority.BROKER,
    "order_state": Authority.LEDGER,
    "control_state": Authority.LEDGER,
    "allowed_rules": Authority.POLICY_BUNDLE,
    "limits": Authority.POLICY_BUNDLE,
    "who_when_why": Authority.AUDIT,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def authoritative_position_quantity(
    *,
    context: MemoryContext,
    broker_snapshot: BrokerPositionSnapshot,
) -> int:
    """컨텍스트 값은 의도적으로 읽지 않는다."""

    _ = context
    return broker_snapshot.quantity


def resolve_submission_snapshot(
    *,
    gui_snapshot: BrokerPositionSnapshot,
    authority_snapshot: BrokerPositionSnapshot,
    decision_time: datetime,
) -> BrokerPositionSnapshot:
    """V3 제출 시 GUI 표시값이 아니라 최신 권위 스냅숏을 사용한다."""

    _ = gui_snapshot
    ensure_snapshot_usable(authority_snapshot, decision_time)
    return authority_snapshot


def require_confirmed_thesis(ref: ConfirmedThesisRef | DraftThesisRef) -> ConfirmedThesisRef:
    if not isinstance(ref, ConfirmedThesisRef):
        raise ConstraintViolation("NO_DRAFT_TO_SIZING")
    return ref


def make_approval(
    *,
    approval_id: str,
    target_id: str,
    target_hash: str,
    approved_by: str,
    decided_at: datetime,
) -> Approval:
    if not target_hash:
        raise ConstraintViolation("approval target hash is required")
    return Approval(approval_id, target_id, target_hash, approved_by, decided_at)


def apply_order_event(order: Order, event: OrderEvent) -> Order:
    allowed = ORDER_TRANSITIONS.get(order.state, {})
    if event not in allowed:
        raise IllegalTransition(f"{order.state.value} + {event.value}")
    next_state = allowed[event]
    return replace(order, state=next_state)


def assign_broker_order_id(
    order: Order,
    *,
    event: Event,
    broker_order_id: str,
) -> Order:
    if event.source is not Authority.BROKER or event.kind not in {
        "BROKER_ACCEPTED",
        "BROKER_ORDER_FOUND",
    }:
        raise ConstraintViolation("broker_order_id must come from broker event")
    if not broker_order_id:
        raise ConstraintViolation("broker_order_id is empty")
    return replace(order, broker_order_id=broker_order_id)


def can_auto_resubmit(order: Order) -> bool:
    return order.state is not OrderState.UNKNOWN


def new_risk_blockers(
    *,
    gate: TradingGateState,
    kill_switch: KillSwitchState,
    reconciliation: ReconciliationState,
    audit_healthy: bool,
    intent_environment: Environment | None = None,
    execution_environment: Environment | None = None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if gate is not TradingGateState.OPEN:
        blockers.append("NO_NEW_RISK_WHEN_GATE_NOT_OPEN")
    if kill_switch is KillSwitchState.ON:
        blockers.append("NO_NEW_RISK_WHEN_KILL_SWITCH_ON")
    if reconciliation is not ReconciliationState.MATCH:
        blockers.append("NO_NEW_RISK_WHEN_RECONCILIATION_NOT_MATCH")
    if not audit_healthy:
        blockers.append("NO_NEW_RISK_WHEN_AUDIT_UNHEALTHY")
    if (
        intent_environment is not None
        and execution_environment is not None
        and intent_environment is not execution_environment
    ):
        blockers.append("NO_IMPLICIT_PAPER_TO_LIVE_PROMOTION")
    return tuple(blockers)


def require_new_risk_allowed(**kwargs: Any) -> None:
    blockers = new_risk_blockers(**kwargs)
    if blockers:
        raise ConstraintViolation(",".join(blockers))


def reconcile_position(*, ledger_qty: int, broker_qty: int) -> ReconciliationOutcome:
    if ledger_qty == broker_qty:
        return ReconciliationOutcome(
            ReconciliationState.MATCH, ledger_qty, broker_qty, False
        )
    return ReconciliationOutcome(
        ReconciliationState.MISMATCH, ledger_qty, broker_qty, True
    )


def create_control_commit(
    *,
    commit_id: str,
    kind: str,
    actor: Actor,
    correlation_id: str,
    audit_healthy: bool,
    committed_at: datetime,
) -> ControlCommit:
    if not audit_healthy:
        raise ConstraintViolation("NO_NEW_RISK_WHEN_AUDIT_UNHEALTHY")
    return ControlCommit(commit_id, kind, actor, committed_at, correlation_id)


def create_economic_commit(*, event: Event) -> EconomicCommit:
    if event.source is not Authority.BROKER:
        raise ConstraintViolation("economic commit requires broker fact")
    allowed = {"BROKER_ACCEPTED", "FILL_RECEIVED", "BROKER_ORDER_FOUND"}
    if event.kind not in allowed:
        raise ConstraintViolation("event is not an economic fact")
    return EconomicCommit(
        commit_id=f"econ:{event.event_id}",
        event_id=event.event_id,
        economic_kind=event.kind,
        committed_at=event.occurred_at,
        correlation_id=event.correlation_id,
    )


def ensure_snapshot_usable(snapshot: BrokerPositionSnapshot, decision_time: datetime) -> None:
    if snapshot.as_of is None or snapshot.fetched_at is None:  # defensive for untyped callers
        raise ConstraintViolation("snapshot requires as_of and fetched_at")
    if snapshot.fetched_at > decision_time:
        raise ConstraintViolation("future fetched_at cannot be used")


def trace_correlation(records: Iterable[TraceRecord], correlation_id: str) -> tuple[TraceRecord, ...]:
    selected = [r for r in records if r.correlation_id == correlation_id]
    return tuple(sorted(selected, key=lambda r: (r.sequence, r.at)))


def authority_for(fact: str) -> Authority:
    try:
        return AUTHORITY_BY_FACT[fact]
    except KeyError as exc:
        raise ExecutionWorldError(f"unknown fact authority: {fact}") from exc


def _load_json_yaml(path: Path) -> dict[str, Any]:
    """Load JSON-compatible YAML without adding PyYAML as a dependency."""

    return json.loads(path.read_text(encoding="utf-8"))


def load_execution_world_config(path: Path) -> dict[str, Any]:
    return _load_json_yaml(path)


def load_core_entities_config(path: Path) -> dict[str, Any]:
    return _load_json_yaml(path)


def validate_execution_world_contract(config: Mapping[str, Any]) -> None:
    expected_order_states = {s.value for s in OrderState}
    actual_order_states = set(config.get("states", {}).get("order", []))
    if actual_order_states != expected_order_states:
        raise ContractValidationError("order states do not match code contract")

    transitions = config.get("transitions", {}).get("order", {})
    # Architecture invariant: a fill cannot happen directly from CREATED.
    created = transitions.get("CREATED", {})
    if set(created) != {"SUBMIT_REQUESTED"}:
        raise ContractValidationError("CREATED may transition only by SUBMIT_REQUESTED")

    submitting = transitions.get("SUBMITTING", {})
    if submitting.get("TIMEOUT") != "UNKNOWN":
        raise ContractValidationError("SUBMITTING timeout must become UNKNOWN")

    expected_transitions = {
        state.value: {event.value: target.value for event, target in mapping.items()}
        for state, mapping in ORDER_TRANSITIONS.items()
    }
    if transitions != expected_transitions:
        raise ContractValidationError("order transition table differs from code contract")

    required_constraints = {
        "NO_DRAFT_TO_SIZING",
        "NO_UNAPPROVED_INTENT",
        "NO_NEW_RISK_WHEN_GATE_NOT_OPEN",
        "NO_NEW_RISK_WHEN_KILL_SWITCH_ON",
        "NO_NEW_RISK_WHEN_RECONCILIATION_NOT_MATCH",
        "NO_NEW_RISK_WHEN_AUDIT_UNHEALTHY",
        "NO_AUTO_RESUBMIT_WHEN_ORDER_UNKNOWN",
        "NO_RAW_SYMBOL_QTY_PRICE_SUBMIT_CLI",
        "NO_IMPLICIT_PAPER_TO_LIVE_PROMOTION",
    }
    actual_constraints = {item["id"] for item in config.get("constraints", [])}
    if not required_constraints <= actual_constraints:
        missing = sorted(required_constraints - actual_constraints)
        raise ContractValidationError(f"missing constraints: {missing}")

    scope = config.get("operating_scope", {})
    if scope.get("human_users") != 1 or scope.get("human_actor_id") != "OWNER":
        raise ContractValidationError("operating scope must have exactly one human OWNER")
    if scope.get("runtime_account_switch") != "DENY":
        raise ContractValidationError("runtime account switching must be denied")

    fixed_accounts = config.get("fixed_accounts", {})
    expected_accounts = {
        "PAPER": fixed_account_ref("PAPER").value,
        "LIVE": fixed_account_ref("LIVE").value,
    }
    if fixed_accounts != expected_accounts:
        raise ContractValidationError("fixed PAPER/LIVE account binding changed")

    if set(config.get("record_types", [])) != {"OBSERVATION", "JUDGMENT", "PROPOSAL", "EVENT"}:
        raise ContractValidationError("record types must remain separate")
    if set(config.get("commit_types", [])) != {"CONTROL_COMMIT", "ECONOMIC_COMMIT"}:
        raise ContractValidationError("commit types must remain separate")


def validate_core_entities_contract(config: Mapping[str, Any]) -> None:
    entities = config.get("entities", {})
    required = {
        "issuer",
        "security",
        "account",
        "position",
        "investment_thesis",
        "order",
        "approval",
    }
    if set(entities) != required:
        raise ContractValidationError("core entity set changed")
    if entities["security"].get("belongs_to") != "issuer":
        raise ContractValidationError("Security must belong to Issuer")
    account = entities["account"]
    if account.get("identity_source") != "fixed_environment_binding":
        raise ContractValidationError("Account identity must come from fixed environment binding")
    if account.get("mode") != "ONE_FIXED_ACCOUNT_PER_ENVIRONMENT":
        raise ContractValidationError("multi-account mode is out of scope")
    if entities["position"].get("economic_authority") != "broker_account":
        raise ContractValidationError("Position economic authority must be broker account")
    if not entities["investment_thesis"].get("draft_is_not_entity"):
        raise ContractValidationError("InvestmentThesisDraft must not be a core entity")
    if entities["order"].get("state_owner") != "ledger.order_store":
        raise ContractValidationError("Order state owner changed")
    if not entities["approval"].get("immutable_target_hash_required"):
        raise ContractValidationError("Approval target hash is required")
