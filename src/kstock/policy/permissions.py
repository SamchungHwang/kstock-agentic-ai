from __future__ import annotations

from .model import (
    AUTOMATION_RANK,
    PermissionDecision,
    PermissionStatus,
    PolicyBundle,
    RiskClass,
    RuntimeControlState,
)


def risk_class_for(bundle: PolicyBundle, action_id: str) -> RiskClass:
    try:
        return bundle.risk_classes[action_id]
    except KeyError as exc:
        raise KeyError(f"undefined action_id: {action_id}") from exc


def assert_runtime_cannot_lower_risk_class(bundle: PolicyBundle, action_id: str, claimed: RiskClass) -> None:
    catalog = risk_class_for(bundle, action_id)
    rank = {RiskClass.R0: 0, RiskClass.R1: 1, RiskClass.R2: 2, RiskClass.R3: 3}
    if rank[claimed] < rank[catalog]:
        raise ValueError(f"runtime risk downgrade forbidden: catalog={catalog}, claimed={claimed}")


def decide_permission(
    *,
    bundle: PolicyBundle,
    runtime: RuntimeControlState,
    action_id: str,
    actor: str,
    owner_approval_present: bool,
) -> PermissionDecision:
    if runtime.environment is not bundle.environment or runtime.account_ref != bundle.account_ref:
        return PermissionDecision(PermissionStatus.BLOCKED, "EXECUTION_WORLD_MISMATCH", action_id)

    risk_class = bundle.risk_classes.get(action_id)
    rule = bundle.permissions.get(action_id)
    if risk_class is None or rule is None:
        return PermissionDecision(PermissionStatus.BLOCKED, "UNKNOWN_ACTION", action_id, risk_class)
    if actor not in rule.actors:
        return PermissionDecision(PermissionStatus.BLOCKED, "ACTOR_FORBIDDEN", action_id, risk_class)

    current = runtime.automation_profile.current_level
    if AUTOMATION_RANK[current] < AUTOMATION_RANK[rule.min_runtime_level]:
        return PermissionDecision(PermissionStatus.BLOCKED, "AUTOMATION_LEVEL_TOO_LOW", action_id, risk_class)
    if AUTOMATION_RANK[current] > AUTOMATION_RANK[rule.max_automation]:
        return PermissionDecision(PermissionStatus.BLOCKED, "AUTOMATION_LEVEL_EXCEEDS_POLICY", action_id, risk_class)
    if rule.owner_approval_required and not owner_approval_present:
        return PermissionDecision(PermissionStatus.BLOCKED, "OWNER_APPROVAL_REQUIRED", action_id, risk_class)
    return PermissionDecision(PermissionStatus.PASS, "PASS", action_id, risk_class)
