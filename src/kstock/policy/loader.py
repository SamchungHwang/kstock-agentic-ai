from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kstock.domain.enums import Environment
from kstock.fixed_identity import fixed_account_ref, normalize_environment

from .model import (
    ActionPermission,
    AutomationLevel,
    KillSwitchState,
    OddPolicy,
    PolicyBundle,
    RiskClass,
    stable_hash,
)


class PolicyLoadError(ValueError):
    pass


_BUNDLE_KEYS = {"version", "policy_id", "policy_version", "environment", "references"}
_REFERENCE_KEYS = {
    "risk_classes",
    "automation_levels",
    "action_permissions",
    "odd",
    "kill_switch",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyLoadError(f"cannot load policy file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyLoadError(f"policy file must contain a mapping: {path}")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], *, label: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise PolicyLoadError(f"{label}: unknown fields: {sorted(unknown)}")
    if missing:
        raise PolicyLoadError(f"{label}: missing fields: {sorted(missing)}")


def load_policy_bundle(bundle_path: Path) -> PolicyBundle:
    bundle_path = bundle_path.resolve()
    raw_bundle = _load_yaml(bundle_path)
    _require_exact_keys(raw_bundle, _BUNDLE_KEYS, label="policy_bundle")
    references = raw_bundle["references"]
    if not isinstance(references, dict):
        raise PolicyLoadError("policy_bundle.references must be a mapping")
    _require_exact_keys(references, _REFERENCE_KEYS, label="policy_bundle.references")

    env_value = normalize_environment(str(raw_bundle["environment"]))
    environment = Environment(env_value)
    account_ref = fixed_account_ref(env_value).value
    base = bundle_path.parent

    raw_risk = _load_yaml(base / str(references["risk_classes"]))
    if set(raw_risk) != {"version", "actions"} or not isinstance(raw_risk["actions"], dict):
        raise PolicyLoadError("risk_classes.yaml must contain only version and actions")
    try:
        risk_classes = {str(action): RiskClass(str(level)) for action, level in raw_risk["actions"].items()}
    except ValueError as exc:
        raise PolicyLoadError(f"invalid RiskClass: {exc}") from exc

    raw_levels = _load_yaml(base / str(references["automation_levels"]))
    if set(raw_levels) != {"version", "defaults"} or not isinstance(raw_levels["defaults"], dict):
        raise PolicyLoadError("automation_levels.yaml must contain only version and defaults")
    if env_value not in raw_levels["defaults"]:
        raise PolicyLoadError(f"missing automation default for {env_value}")
    try:
        default_automation = AutomationLevel(str(raw_levels["defaults"][env_value]))
    except ValueError as exc:
        raise PolicyLoadError(f"invalid AutomationLevel: {exc}") from exc

    raw_permissions = _load_yaml(base / str(references["action_permissions"]))
    if set(raw_permissions) != {"version", "permissions"} or not isinstance(raw_permissions["permissions"], dict):
        raise PolicyLoadError("action_permissions.yaml must contain only version and permissions")
    permissions: dict[str, ActionPermission] = {}
    for action_id, per_env in raw_permissions["permissions"].items():
        if action_id not in risk_classes:
            raise PolicyLoadError(f"undefined action_id in permissions: {action_id}")
        if not isinstance(per_env, dict) or env_value not in per_env:
            raise PolicyLoadError(f"missing {env_value} permission for action: {action_id}")
        rule = per_env[env_value]
        if not isinstance(rule, dict):
            raise PolicyLoadError(f"permission rule must be mapping: {action_id}/{env_value}")
        allowed_keys = {"max_automation", "actors", "owner_approval_required", "min_runtime_level"}
        unknown = set(rule) - allowed_keys
        if unknown:
            raise PolicyLoadError(f"unknown permission fields for {action_id}: {sorted(unknown)}")
        actors = rule.get("actors", [])
        if not isinstance(actors, list) or not actors:
            raise PolicyLoadError(f"actors must be non-empty list: {action_id}")
        try:
            permissions[str(action_id)] = ActionPermission(
                max_automation=AutomationLevel(str(rule["max_automation"])),
                min_runtime_level=AutomationLevel(str(rule.get("min_runtime_level", "A0"))),
                actors=frozenset(str(actor) for actor in actors),
                owner_approval_required=bool(rule.get("owner_approval_required", False)),
            )
        except (KeyError, ValueError) as exc:
            raise PolicyLoadError(f"invalid permission for {action_id}: {exc}") from exc

    missing_permissions = set(risk_classes) - set(permissions)
    if missing_permissions:
        raise PolicyLoadError(f"missing permissions for actions: {sorted(missing_permissions)}")

    raw_odd = _load_yaml(base / str(references["odd"]))
    if set(raw_odd) != {"version", "environments"} or not isinstance(raw_odd["environments"], dict):
        raise PolicyLoadError("odd.yaml must contain only version and environments")
    env_odd = raw_odd["environments"].get(env_value)
    if not isinstance(env_odd, dict):
        raise PolicyLoadError(f"missing ODD for {env_value}")
    expected_odd_keys = {
        "account_ref", "market", "products", "sessions", "order_types", "data", "long_only",
        "short_sell_enabled", "derivatives_enabled",
    }
    _require_exact_keys(env_odd, expected_odd_keys, label=f"odd.{env_value}")
    data = env_odd["data"]
    if not isinstance(data, dict) or set(data) != {
        "quote_max_age_seconds", "account_max_age_seconds", "open_orders_max_age_seconds"
    }:
        raise PolicyLoadError(f"odd.{env_value}.data has invalid fields")
    odd = OddPolicy(
        environment=environment,
        account_ref=str(env_odd["account_ref"]),
        market=str(env_odd["market"]),
        products=frozenset(str(v) for v in env_odd["products"]),
        sessions=frozenset(str(v) for v in env_odd["sessions"]),
        order_types=frozenset(str(v) for v in env_odd["order_types"]),
        quote_max_age_seconds=int(data["quote_max_age_seconds"]),
        account_max_age_seconds=int(data["account_max_age_seconds"]),
        open_orders_max_age_seconds=int(data["open_orders_max_age_seconds"]),
        long_only=bool(env_odd["long_only"]),
        short_sell_enabled=bool(env_odd["short_sell_enabled"]),
        derivatives_enabled=bool(env_odd["derivatives_enabled"]),
    )
    if odd.account_ref != account_ref:
        raise PolicyLoadError(
            f"ODD account_ref mismatch for {env_value}: expected={account_ref}, actual={odd.account_ref}"
        )

    raw_kill = _load_yaml(base / str(references["kill_switch"]))
    if set(raw_kill) != {"version", "states"} or not isinstance(raw_kill["states"], dict):
        raise PolicyLoadError("kill_switch.yaml must contain only version and states")
    try:
        kill_states = frozenset(KillSwitchState(str(name)) for name in raw_kill["states"])
    except ValueError as exc:
        raise PolicyLoadError(f"invalid kill switch state: {exc}") from exc
    required_states = frozenset({
        KillSwitchState.NORMAL,
        KillSwitchState.NO_NEW_RISK,
        KillSwitchState.HARD_FROZEN,
    })
    if kill_states != required_states:
        raise PolicyLoadError("kill_switch.yaml must define NORMAL, NO_NEW_RISK, HARD_FROZEN exactly")

    policy_hash = stable_hash({
        "bundle": raw_bundle,
        "risk_classes": raw_risk,
        "automation_levels": raw_levels,
        "action_permissions": raw_permissions,
        "odd": raw_odd,
        "kill_switch": raw_kill,
    })
    return PolicyBundle(
        policy_id=str(raw_bundle["policy_id"]),
        policy_version=str(raw_bundle["policy_version"]),
        environment=environment,
        account_ref=account_ref,
        risk_classes=risk_classes,
        permissions=permissions,
        default_automation=default_automation,
        odd=odd,
        kill_switch_states=kill_states,
        policy_hash=policy_hash,
    )
