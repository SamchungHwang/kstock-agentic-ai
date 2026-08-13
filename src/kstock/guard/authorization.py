from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from kstock.domain.enums import ActorRole


@dataclass(frozen=True, kw_only=True)
class AuthorizationPolicy:
    """단일 사용자(OWNER) + 내부 서비스 주체용 권한 계약."""

    command_roles: Mapping[str, frozenset[ActorRole]]
    human_only_commands: frozenset[str]
    owner_approval_commands: frozenset[str] = frozenset()
