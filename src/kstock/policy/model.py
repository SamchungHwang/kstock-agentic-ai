from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from kstock.domain.enums import Environment, RiskDirection
from kstock.fixed_identity import assert_fixed_account_binding


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class AutomationLevel(StrEnum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"



class OddStatus(StrEnum):
    IN_ODD = "IN_ODD"
    OUT_OF_ODD = "OUT_OF_ODD"
    UNKNOWN = "UNKNOWN"


class KillSwitchState(StrEnum):
    NORMAL = "NORMAL"
    NO_NEW_RISK = "NO_NEW_RISK"
    HARD_FROZEN = "HARD_FROZEN"


class PermissionStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


AUTOMATION_RANK: Mapping[AutomationLevel, int] = {
    AutomationLevel.A0: 0,
    AutomationLevel.A1: 1,
    AutomationLevel.A2: 2,
    AutomationLevel.A3: 3,
}

KILL_SWITCH_RANK: Mapping[KillSwitchState, int] = {
    KillSwitchState.NORMAL: 0,
    KillSwitchState.NO_NEW_RISK: 1,
    KillSwitchState.HARD_FROZEN: 2,
}


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ActionPermission:
    max_automation: AutomationLevel
    actors: frozenset[str]
    owner_approval_required: bool = False
    min_runtime_level: AutomationLevel = AutomationLevel.A0


@dataclass(frozen=True, slots=True)
class OddPolicy:
    environment: Environment
    account_ref: str
    market: str
    products: frozenset[str]
    sessions: frozenset[str]
    order_types: frozenset[str]
    quote_max_age_seconds: int
    account_max_age_seconds: int
    open_orders_max_age_seconds: int
    long_only: bool
    short_sell_enabled: bool
    derivatives_enabled: bool

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    policy_id: str
    policy_version: str
    environment: Environment
    account_ref: str
    risk_classes: Mapping[str, RiskClass]
    permissions: Mapping[str, ActionPermission]
    default_automation: AutomationLevel
    odd: OddPolicy
    kill_switch_states: frozenset[KillSwitchState]
    policy_hash: str

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True, slots=True)
class AutomationProfile:
    current_level: AutomationLevel
    source: str
    changed_at: datetime
    evidence_id: str | None = None
    approval_id: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeControlState:
    environment: Environment
    account_ref: str
    control_version: int
    kill_switch_state: KillSwitchState
    automation_profile: AutomationProfile
    odd_status: OddStatus = OddStatus.UNKNOWN

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)
        if self.control_version < 0:
            raise ValueError("control_version must be >= 0")


@dataclass(frozen=True, slots=True)
class PositionState:
    symbol: str
    quantity: int


@dataclass(frozen=True, slots=True)
class AccountStateSnapshot:
    account_ref: str
    positions: tuple[PositionState, ...]
    as_of: datetime
    fetched_at: datetime
    available: bool = True

    def quantity(self, symbol: str) -> int:
        for position in self.positions:
            if position.symbol == symbol:
                return position.quantity
        return 0


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    symbol: str
    price: int
    as_of: datetime
    fetched_at: datetime
    available: bool = True


@dataclass(frozen=True, slots=True)
class OpenOrderState:
    order_id: str
    symbol: str
    side: str
    remaining_qty: int


@dataclass(frozen=True, slots=True)
class OpenOrdersSnapshot:
    account_ref: str
    orders: tuple[OpenOrderState, ...]
    as_of: datetime
    fetched_at: datetime
    available: bool = True

    def find(self, order_id: str) -> OpenOrderState | None:
        for order in self.orders:
            if order.order_id == order_id:
                return order
        return None


@dataclass(frozen=True, slots=True)
class RiskDirectionAssessment:
    direction: RiskDirection
    assessment_hash: str
    assessed_at: datetime
    account_as_of: datetime | None
    open_orders_as_of: datetime | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApprovalRiskBinding:
    approval_id: str
    proposal_hash: str
    environment: Environment
    account_ref: str
    approved_direction: RiskDirection
    approved_assessment_hash: str
    approved_by: str
    approved_at: datetime

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True, slots=True)
class ExecutionPermit:
    permit_id: str
    intent_id: str
    environment: Environment
    account_ref: str
    policy_version: str
    bound_control_version: int
    issued_at: datetime

    def __post_init__(self) -> None:
        assert_fixed_account_binding(self.environment.value, self.account_ref)


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    status: PermissionStatus
    code: str
    action_id: str
    risk_class: RiskClass | None = None


@dataclass(frozen=True, slots=True)
class OddResult:
    status: OddStatus
    reasons: tuple[str, ...]
    recommended_kill_switch: KillSwitchState | None = None


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    evidence_id: str
    paper_cases: int
    shadow_cases: int
    blocked_cases: int
    critical_incidents: int
    source_event_count: int
    source_digest: str
    generated_at: datetime
    metrics: Mapping[str, int] = field(default_factory=dict)
