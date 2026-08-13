from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ConsoleVersion(str, Enum):
    V1 = "V1"
    V2 = "V2"
    V3_PAPER = "V3_PAPER"


_VERSION_RANK = {
    ConsoleVersion.V1: 1,
    ConsoleVersion.V2: 2,
    ConsoleVersion.V3_PAPER: 3,
}


class ResponseKind(str, Enum):
    OK = "OK"
    REFUSAL = "REFUSAL"
    INCOMPLETE = "INCOMPLETE"
    API_ERROR = "API_ERROR"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


class GuardState(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


class SubmitStatus(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ContractError(ValueError):
    pass


class CapabilityError(ContractError):
    pass


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class JudgeRunResult:
    evidence_packet_id: str
    strategy_id: str
    response_kind: ResponseKind
    draft_id: str | None
    message: str


@dataclass(frozen=True)
class InvestmentThesisDraft:
    draft_id: str
    payload: dict[str, Any]
    response_kind: ResponseKind = ResponseKind.OK


@dataclass(frozen=True)
class InvestmentThesis:
    thesis_id: str
    draft_id: str
    payload: dict[str, Any]
    thesis_hash: str


@dataclass(frozen=True)
class SizingResult:
    sizing_id: str
    thesis_id: str
    account_snapshot_id: str
    policy_version: str
    inputs: dict[str, Any]
    formula: str
    limiting_factor: str
    qty: int
    limit_price: int
    result_hash: str


@dataclass(frozen=True)
class OrderProposal:
    proposal_id: str
    thesis_id: str
    sizing_id: str
    symbol: str
    qty: int
    limit_price: int
    proposal_hash: str
    created_at: datetime


@dataclass(frozen=True)
class ProposalDecision:
    event_id: str
    proposal_id: str
    proposal_hash: str
    decision: Decision
    reason: str
    decided_at: datetime


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    proposal_id: str
    proposal_hash: str
    environment: str
    account_ref: str
    symbol: str
    qty: int
    limit_price: int
    issued_at: datetime
    expires_at: datetime
    intent_hash: str


@dataclass(frozen=True)
class BrokerOrderResult:
    status: SubmitStatus
    code: str
    intent_id: str
    broker_order_id: str | None = None
    automatic_retry: bool = False


@dataclass(frozen=True)
class PromotionEvidence:
    v1_safe_operations_passed: bool
    reconciliation_clean: bool
    audit_healthy: bool
    kill_switch_off: bool
    no_unknown_orders: bool
    v2_contract_tests_passed: bool
    paper_environment: bool

    def broker_submit_enabled(self) -> bool:
        return all((
            self.v1_safe_operations_passed,
            self.reconciliation_clean,
            self.audit_healthy,
            self.kill_switch_off,
            self.no_unknown_orders,
            self.v2_contract_tests_passed,
            self.paper_environment,
        ))


@dataclass
class SubmissionRegistry:
    submitted_intents: set[str] = field(default_factory=set)

    def mark_submitted(self, intent_id: str) -> None:
        self.submitted_intents.add(intent_id)

    def was_submitted(self, intent_id: str) -> bool:
        return intent_id in self.submitted_intents


def require_version(actual: ConsoleVersion, minimum: ConsoleVersion) -> None:
    if _VERSION_RANK[actual] < _VERSION_RANK[minimum]:
        raise CapabilityError(f"{minimum.value} capability required; actual={actual.value}")


def load_contracts(root: Path) -> dict[str, Any]:
    contracts = root / "contracts"
    names = [
        "console_v2_v3_screen.json",
        "cli_io_contracts.json",
        "button_permission_risk_map.json",
        "feature_promotion.json",
    ]
    return {
        name: json.loads((contracts / name).read_text(encoding="utf-8"))
        for name in names
    }
