from __future__ import annotations

from enum import Enum


class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ActorType(str, Enum):
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"


class ActorRole(str, Enum):
    # 사람 사용자는 OWNER 한 명뿐이다.
    OWNER = "OWNER"
    # 내부 작업 프로세스. 사람 사용자가 아니다.
    SERVICE = "SERVICE"
    # 자동 강화/정지 전용 서비스 역할. 완화·승격 권한은 갖지 않는다.
    SYSTEM_GUARDIAN = "SYSTEM_GUARDIAN"


class ThesisStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"


class RiskDirection(str, Enum):
    INCREASE = "INCREASE"
    NEUTRAL = "NEUTRAL"
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
