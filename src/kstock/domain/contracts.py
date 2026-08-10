from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .enums import Environment


@dataclass(frozen=True, kw_only=True)
class Contract:
    contract_id: str
    schema_version: int
    as_of: datetime
    created_at: datetime
    actor_id: str
    produced_by: str
    environment: Environment
    correlation_id: str
    contract_hash: str
    policy_version: str | None = None


@dataclass(frozen=True, kw_only=True)
class InvalidationPredicate:
    field: str
    operator: str
    threshold: Decimal
    unit: str
    window: str


@dataclass(frozen=True, kw_only=True)
class InvestmentThesis(Contract):
    security_id: str
    thesis_text: str
    conviction: Decimal
    invalidation_predicate: InvalidationPredicate
    invalidation_text: str | None
    evidence_ids: tuple[str, ...]
    model_provider: str
    model_name: str
    model_version: str
