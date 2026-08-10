from __future__ import annotations

from enum import Enum


class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ActorType(str, Enum):
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"


class ActorRole(str, Enum):
    APPROVER = "APPROVER"
    SUBMITTER = "SUBMITTER"
    SERVICE = "SERVICE"


class ThesisStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"


class RiskDirection(str, Enum):
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class GuardStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class GuardCode(str, Enum):
    PASS = "PASS"
    STATE_UNAVAILABLE = "STATE_UNAVAILABLE"
    ACTOR_UNAUTHENTICATED = "ACTOR_UNAUTHENTICATED"
    ACTOR_ROLE_FORBIDDEN = "ACTOR_ROLE_FORBIDDEN"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class RecoveryClass(str, Enum):
    RETRYABLE = "RETRYABLE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
