from __future__ import annotations

from dataclasses import dataclass

from .enums import ActorRole, ActorType


@dataclass(frozen=True, kw_only=True)
class Actor:
    actor_id: str
    actor_type: ActorType
    authenticated: bool
    roles: frozenset[ActorRole]
