from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .enums import ThesisStatus


@dataclass(frozen=True, kw_only=True)
class ThesisLifecycleState:
    thesis_id: str
    status: ThesisStatus
    changed_at: datetime
    reason_code: str
    superseded_by: str | None = None


def invalidate_thesis(
    state: ThesisLifecycleState,
    *,
    changed_at: datetime,
    reason_code: str,
) -> ThesisLifecycleState:
    if state.status is ThesisStatus.SUPERSEDED:
        raise ValueError("SUPERSEDED thesis cannot be invalidated")
    return replace(
        state,
        status=ThesisStatus.INVALIDATED,
        changed_at=changed_at,
        reason_code=reason_code,
        superseded_by=None,
    )


def supersede_thesis(
    state: ThesisLifecycleState,
    *,
    replacement_thesis_id: str,
    changed_at: datetime,
) -> ThesisLifecycleState:
    if replacement_thesis_id == state.thesis_id:
        raise ValueError("replacement thesis must differ from old thesis")
    return replace(
        state,
        status=ThesisStatus.SUPERSEDED,
        changed_at=changed_at,
        reason_code="SUPERSEDED",
        superseded_by=replacement_thesis_id,
    )
