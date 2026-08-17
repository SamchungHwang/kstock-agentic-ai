from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml

from kstock.domain.enums import Environment
from kstock.fixed_identity import assert_fixed_account_binding
from kstock.policy.loader import PolicyLoadError, load_policy_bundle
from kstock.policy.model import AutomationLevel, RiskClass
from kstock.policy.permissions import assert_runtime_cannot_lower_risk_class, decide_permission
from kstock.policy.runtime_control import RuntimeControlStore


def test_01_undefined_action_id_fails_policy_bundle_load(ch7_root: Path, tmp_path: Path) -> None:
    source = ch7_root / "config" / "policy"
    for name in [
        "policy_bundle.paper.yaml", "risk_classes.yaml", "automation_levels.yaml",
        "action_permissions.yaml", "odd.yaml", "kill_switch.yaml",
    ]:
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    permissions_path = tmp_path / "action_permissions.yaml"
    raw = yaml.safe_load(permissions_path.read_text(encoding="utf-8"))
    raw["permissions"]["NOT_REGISTERED_ACTION"] = {
        "PAPER": {"min_runtime_level": "A0", "max_automation": "A0", "actors": ["OWNER"]},
        "LIVE": {"min_runtime_level": "A0", "max_automation": "A0", "actors": ["OWNER"]},
    }
    permissions_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="undefined action_id"):
        load_policy_bundle(tmp_path / "policy_bundle.paper.yaml")


def test_02_risk_class_is_catalog_owned_and_runtime_cannot_downgrade(paper_policy) -> None:
    assert paper_policy.risk_classes["BROKER_SUBMIT"] is RiskClass.R3
    with pytest.raises(ValueError, match="downgrade forbidden"):
        assert_runtime_cannot_lower_risk_class(paper_policy, "BROKER_SUBMIT", RiskClass.R2)


def test_03_paper_and_live_each_bind_one_fixed_account(paper_policy, live_policy) -> None:
    assert paper_policy.account_ref == "PAPER_PRIMARY"
    assert live_policy.account_ref == "LIVE_PRIMARY"
    assert paper_policy.odd.account_ref == "PAPER_PRIMARY"
    assert live_policy.odd.account_ref == "LIVE_PRIMARY"
    with pytest.raises(ValueError):
        assert_fixed_account_binding("LIVE", "PAPER_PRIMARY")


def test_04_runtime_account_switch_inputs_do_not_exist(ch7_root: Path) -> None:
    searched = [
        ch7_root / "tools" / "console.py",
        ch7_root / "tools" / "console_commands.py",
        ch7_root / "src" / "kstock" / "cli.py",
        ch7_root / "src" / "kstock" / "console_commands.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in searched)
    assert "--account" not in text
    assert "account_alias" not in text
    assert "account selector" not in text.lower()


def test_05_paper_approval_or_intent_cannot_bind_to_live_world() -> None:
    from datetime import datetime, timezone
    from kstock.policy.model import ApprovalRiskBinding, RiskDirection

    approval = ApprovalRiskBinding(
        approval_id="appr1",
        proposal_hash="p1",
        environment=Environment.PAPER,
        account_ref="PAPER_PRIMARY",
        approved_direction=RiskDirection.INCREASE,
        approved_assessment_hash="h1",
        approved_by="OWNER",
        approved_at=datetime.now(timezone.utc),
    )
    assert approval.environment is Environment.PAPER
    with pytest.raises(ValueError, match="fixed account binding mismatch"):
        ApprovalRiskBinding(
            approval_id="bad",
            proposal_hash="p1",
            environment=Environment.LIVE,
            account_ref="PAPER_PRIMARY",
            approved_direction=RiskDirection.INCREASE,
            approved_assessment_hash="h1",
            approved_by="OWNER",
            approved_at=datetime.now(timezone.utc),
        )


def test_06_permission_uses_runtime_automation_not_caller_argument(paper_policy) -> None:
    signature = inspect.signature(decide_permission)
    assert "automation_level" not in signature.parameters
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A1)
    decision = decide_permission(
        bundle=paper_policy,
        runtime=store.read(),
        action_id="BROKER_SUBMIT",
        actor="SERVICE",
        owner_approval_present=True,
    )
    assert decision.code == "AUTOMATION_LEVEL_TOO_LOW"


def test_07_broker_submit_requires_owner_approval(paper_policy) -> None:
    store = RuntimeControlStore(environment=Environment.PAPER, initial_level=AutomationLevel.A2)
    decision = decide_permission(
        bundle=paper_policy,
        runtime=store.read(),
        action_id="BROKER_SUBMIT",
        actor="SERVICE",
        owner_approval_present=False,
    )
    assert decision.code == "OWNER_APPROVAL_REQUIRED"
