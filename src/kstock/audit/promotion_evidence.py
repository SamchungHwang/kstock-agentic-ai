from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from kstock.policy.model import PromotionEvidence, stable_hash

from .policy_events import PolicyAuditEvent, event_to_dict


class PromotionEvidenceError(ValueError):
    pass


class PromotionEvidenceBuilder:
    """검증된 감사 이벤트만 입력으로 받아 승격 증거를 계산한다.

    paper_cases 같은 수기 카운터를 인자로 받는 API를 의도적으로 제공하지 않는다.
    """

    def build(self, events: Iterable[PolicyAuditEvent]) -> PromotionEvidence:
        items = list(events)
        paper_cases = sum(1 for e in items if e.event_type == "PAPER_CASE_COMPLETED")
        shadow_cases = sum(1 for e in items if e.event_type == "SHADOW_CASE_COMPLETED")
        blocked_cases = sum(1 for e in items if e.event_type == "EXPECTED_BLOCK")
        critical_incidents = sum(1 for e in items if e.event_type == "CRITICAL_INCIDENT")
        digest = stable_hash([event_to_dict(e) for e in items])
        return PromotionEvidence(
            evidence_id=f"promotion_{digest[:12]}",
            paper_cases=paper_cases,
            shadow_cases=shadow_cases,
            blocked_cases=blocked_cases,
            critical_incidents=critical_incidents,
            source_event_count=len(items),
            source_digest=digest,
            generated_at=datetime.now(timezone.utc),
            metrics={
                "paper_cases": paper_cases,
                "shadow_cases": shadow_cases,
                "blocked_cases": blocked_cases,
                "critical_incidents": critical_incidents,
            },
        )
