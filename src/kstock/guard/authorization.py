from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from kstock.domain.enums import ActorRole


@dataclass(frozen=True, kw_only=True)
class AuthorizationPolicy:
    command_roles: Mapping[str, frozenset[ActorRole]]
    human_only_commands: frozenset[str]
    allow_separate_approver_and_submitter: bool = False
