"""Shared domain contract metadata."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class ContractMeta:
    contract_id: str
    schema_version: str
    as_of: datetime
    produced_by: str
    policy_version: str
