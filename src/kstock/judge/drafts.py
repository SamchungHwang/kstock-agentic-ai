from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, kw_only=True)
class PredicateDraft:
    field: str
    operator: str
    threshold: Decimal
    unit: str
    window: str


@dataclass(frozen=True, kw_only=True)
class InvestmentThesisDraft:
    security_id: str
    thesis_text: str
    conviction: Decimal
    invalidation_predicate: PredicateDraft | None
    invalidation_text: str | None
    evidence_ids: tuple[str, ...]
