from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ReevaluationRequest:
    security_id: str
    thesis_id: str
    reason_code: str


def evaluate_invalidation(*, security_id: str, thesis_id: str, matched: bool) -> ReevaluationRequest | None:
    if not matched:
        return None
    return ReevaluationRequest(
        security_id=security_id,
        thesis_id=thesis_id,
        reason_code="THESIS_INVALIDATED",
    )
