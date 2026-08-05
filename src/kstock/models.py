from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RiskClass(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class LockGroup(str, Enum):
    STARTUP = "STARTUP"
    QUERY = "QUERY"
    RECONCILE = "RECONCILE"
    KILL_SWITCH = "KILL_SWITCH"
    AUDIT = "AUDIT"
    ORDERS = "ORDERS"
    DEMO = "DEMO"
    EMERGENCY = "EMERGENCY"


class ResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


EXIT_CODE_BY_STATUS = {
    ResultStatus.SUCCESS: 0,
    ResultStatus.ERROR: 1,
    ResultStatus.BLOCKED: 2,
    ResultStatus.UNKNOWN: 3,
}


@dataclass(frozen=True)
class CommandContext:
    environment: str
    correlation_id: str
    values: dict[str, Any]


@dataclass(frozen=True)
class CliEvent:
    kind: str
    correlation_id: str
    raw: dict[str, Any]
