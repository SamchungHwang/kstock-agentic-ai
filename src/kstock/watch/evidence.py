from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class EvidencePacket:
    security_id: str
    as_of: datetime
    evidence_ids: tuple[str, ...]
    facts: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
