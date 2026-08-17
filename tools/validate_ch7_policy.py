from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _bootstrap() -> None:
    import sys
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result.add(node.module)
    return result


def main() -> int:
    _bootstrap()
    from kstock.audit.promotion_evidence import PromotionEvidenceBuilder
    from kstock.policy.loader import load_policy_bundle
    from kstock.policy.model import AutomationLevel, KillSwitchState, RiskClass

    policy_dir = ROOT / "config" / "policy"
    paper = load_policy_bundle(policy_dir / "policy_bundle.paper.yaml")
    live = load_policy_bundle(policy_dir / "policy_bundle.live.yaml")

    assert paper.account_ref == "PAPER_PRIMARY"
    assert live.account_ref == "LIVE_PRIMARY"
    assert paper.default_automation is AutomationLevel.A1
    assert live.default_automation is AutomationLevel.A0
    assert paper.risk_classes["BROKER_SUBMIT"] is RiskClass.R3
    assert paper.permissions["BROKER_SUBMIT"].owner_approval_required
    assert paper.permissions["BROKER_SUBMIT"].min_runtime_level is AutomationLevel.A2
    assert paper.kill_switch_states == frozenset({
        KillSwitchState.NORMAL,
        KillSwitchState.NO_NEW_RISK,
        KillSwitchState.HARD_FROZEN,
    })

    safety_imports = _imports(ROOT / "src" / "kstock" / "safety" / "kernel.py")
    forbidden = {name for name in safety_imports if name.startswith(("kstock.broker", "kstock.judge", "kstock.portfolio"))}
    assert not forbidden, f"Safety Kernel forbidden imports: {sorted(forbidden)}"

    console_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "tools" / "console.py",
            ROOT / "tools" / "console_commands.py",
            ROOT / "src" / "kstock" / "cli.py",
        ]
    )
    assert "--account" not in console_text
    assert "account_alias" not in console_text

    build_params = list(inspect.signature(PromotionEvidenceBuilder().build).parameters)
    assert build_params == ["events"], build_params

    chapter7_files = [
        ROOT / "src" / "kstock" / "policy" / "model.py",
        ROOT / "src" / "kstock" / "policy" / "runtime_control.py",
        ROOT / "src" / "kstock" / "policy" / "permissions.py",
        ROOT / "src" / "kstock" / "policy" / "odd.py",
        ROOT / "src" / "kstock" / "policy" / "approval.py",
        ROOT / "src" / "kstock" / "policy" / "resume.py",
        ROOT / "src" / "kstock" / "policy" / "pretrade.py",
        ROOT / "src" / "kstock" / "guard" / "risk_direction.py",
        ROOT / "src" / "kstock" / "safety" / "kernel.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in chapter7_files)
    assert "control_epoch" not in text
    assert "global_epoch" not in text
    assert "account_epoch" not in text

    print("Chapter 7 policy/runtime checks: PASS")
    print(f"  PAPER: {paper.policy_version} / {paper.account_ref} / default {paper.default_automation.value}")
    print(f"  LIVE : {live.policy_version} / {live.account_ref} / default {live.default_automation.value}")
    print("  Control term: control_version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
