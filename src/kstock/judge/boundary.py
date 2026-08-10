from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from kstock.domain.contracts import InvalidationPredicate, InvestmentThesis
from kstock.domain.enums import Environment
from kstock.judge.drafts import InvestmentThesisDraft, PredicateDraft


_ALLOWED_OPERATORS = {"LT", "LE", "GT", "GE", "EQ", "NE"}


@dataclass(frozen=True, kw_only=True)
class BoundaryContext:
    as_of: datetime
    actor_id: str
    environment: Environment
    correlation_id: str
    policy_version: str | None
    model_provider: str
    model_name: str
    model_version: str


@dataclass(frozen=True, kw_only=True)
class BoundaryResult:
    status: str
    code: str
    thesis: InvestmentThesis | None


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _validate_predicate(predicate: PredicateDraft) -> bool:
    return bool(
        predicate.field.strip()
        and predicate.operator in _ALLOWED_OPERATORS
        and predicate.unit.strip()
        and predicate.window.strip()
    )


def _canonical_payload(draft: InvestmentThesisDraft, context: BoundaryContext) -> dict[str, object]:
    predicate = draft.invalidation_predicate
    assert predicate is not None
    return {
        "security_id": draft.security_id,
        "thesis_text": draft.thesis_text,
        "conviction": _decimal_text(draft.conviction),
        "invalidation_predicate": {
            "field": predicate.field,
            "operator": predicate.operator,
            "threshold": _decimal_text(predicate.threshold),
            "unit": predicate.unit,
            "window": predicate.window,
        },
        "invalidation_text": draft.invalidation_text,
        "evidence_ids": list(draft.evidence_ids),
        "as_of": context.as_of.isoformat(),
        "actor_id": context.actor_id,
        "environment": context.environment.value,
        "correlation_id": context.correlation_id,
        "policy_version": context.policy_version,
        "model_provider": context.model_provider,
        "model_name": context.model_name,
        "model_version": context.model_version,
    }


def cross_boundary(draft: InvestmentThesisDraft, context: BoundaryContext) -> BoundaryResult:
    """Issue a thesis only from an explicitly structured draft.

    Natural-language invalidation text is documentary data. This function never
    parses percentages, numbers, operators, or windows from free text.
    """
    if not isinstance(draft, InvestmentThesisDraft):
        return BoundaryResult(status="BLOCKED", code="INVALID_DRAFT_TYPE", thesis=None)

    predicate = draft.invalidation_predicate
    if predicate is None:
        return BoundaryResult(
            status="BLOCKED",
            code="INVALIDATION_PREDICATE_REQUIRED",
            thesis=None,
        )

    if not _validate_predicate(predicate):
        return BoundaryResult(status="BLOCKED", code="INVALIDATION_PREDICATE_INVALID", thesis=None)

    if not (Decimal("0") <= draft.conviction <= Decimal("1")):
        return BoundaryResult(status="BLOCKED", code="CONVICTION_OUT_OF_RANGE", thesis=None)

    payload = _canonical_payload(draft, context)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contract_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    contract_id = str(uuid5(NAMESPACE_URL, f"kstock:thesis:{contract_hash}"))

    thesis = InvestmentThesis(
        contract_id=contract_id,
        schema_version=1,
        as_of=context.as_of,
        created_at=context.as_of,
        actor_id=context.actor_id,
        produced_by="kstock.judge.boundary",
        environment=context.environment,
        correlation_id=context.correlation_id,
        contract_hash=contract_hash,
        policy_version=context.policy_version,
        security_id=draft.security_id,
        thesis_text=draft.thesis_text,
        conviction=draft.conviction,
        invalidation_predicate=InvalidationPredicate(
            field=predicate.field,
            operator=predicate.operator,
            threshold=predicate.threshold,
            unit=predicate.unit,
            window=predicate.window,
        ),
        invalidation_text=draft.invalidation_text,
        evidence_ids=tuple(draft.evidence_ids),
        model_provider=context.model_provider,
        model_name=context.model_name,
        model_version=context.model_version,
    )
    return BoundaryResult(status="PASS", code="PASS", thesis=thesis)
