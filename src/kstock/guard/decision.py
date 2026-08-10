from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kstock.domain.actors import Actor
from kstock.domain.enums import ActorRole, ActorType, GuardCode, GuardStatus
from kstock.guard.authorization import AuthorizationPolicy


class AuthoritativeStateProvider(Protocol):
    def load_authoritative_state(self, security_id: str) -> object: ...


@dataclass(frozen=True, kw_only=True)
class GuardInput:
    command: str
    security_id: str
    actor: Actor
    approved_by: Actor | None
    intent_id: str


@dataclass(frozen=True, kw_only=True)
class GuardDecision:
    status: GuardStatus
    code: GuardCode


def _blocked(code: GuardCode) -> GuardDecision:
    return GuardDecision(status=GuardStatus.BLOCKED, code=code)


def evaluate_guard(
    guard_input: GuardInput,
    *,
    state_provider: AuthoritativeStateProvider,
    authorization_policy: AuthorizationPolicy,
) -> GuardDecision:
    try:
        authoritative_state = state_provider.load_authoritative_state(guard_input.security_id)
    except Exception:
        return _blocked(GuardCode.STATE_UNAVAILABLE)

    if authoritative_state is None:
        return _blocked(GuardCode.STATE_UNAVAILABLE)

    actor = guard_input.actor
    if not actor.authenticated:
        return _blocked(GuardCode.ACTOR_UNAUTHENTICATED)

    if guard_input.command in authorization_policy.human_only_commands and actor.actor_type is not ActorType.HUMAN:
        return _blocked(GuardCode.ACTOR_ROLE_FORBIDDEN)

    required_roles = authorization_policy.command_roles.get(guard_input.command, frozenset())
    if required_roles and actor.roles.isdisjoint(required_roles):
        return _blocked(GuardCode.ACTOR_ROLE_FORBIDDEN)

    approver = guard_input.approved_by
    if approver is not None:
        if not approver.authenticated:
            return _blocked(GuardCode.ACTOR_UNAUTHENTICATED)
        if ActorRole.APPROVER not in approver.roles:
            return _blocked(GuardCode.ACTOR_ROLE_FORBIDDEN)
        if approver.actor_id != actor.actor_id and not authorization_policy.allow_separate_approver_and_submitter:
            return _blocked(GuardCode.ACTOR_ROLE_FORBIDDEN)

    return GuardDecision(status=GuardStatus.PASS, code=GuardCode.PASS)
