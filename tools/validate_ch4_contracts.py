from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kstock.v2v3_contracts import load_contracts


def validate() -> list[str]:
    problems: list[str] = []
    data = load_contracts(ROOT)
    screen = data["console_v2_v3_screen.json"]
    cli = data["cli_io_contracts.json"]
    buttons = data["button_permission_risk_map.json"]
    promotion = data["feature_promotion.json"]

    if screen["versions"]["V3_PAPER"]["forbidden"] and "RAW_ORDER_INPUT" not in screen["versions"]["V3_PAPER"]["forbidden"]:
        problems.append("V3 must forbid RAW_ORDER_INPUT")
    submit = cli["commands"]["order submit-approved"]
    if submit["inputs"] != ["intent_id"]:
        problems.append("submit-approved must accept intent_id only")
    for arg in ("symbol", "qty", "price"):
        if arg not in submit["forbidden_args"]:
            problems.append(f"submit-approved must forbid {arg}")
    if submit.get("automatic_retry_on_unknown") is not False:
        problems.append("UNKNOWN submit must not auto-retry")

    by_key = {b["key"]: b for b in buttons["buttons"]}
    if not by_key["halt_trading"]["always_available"]:
        problems.append("halt_trading must always be available")
    if not by_key["cancel_open_order"]["always_available"]:
        problems.append("cancel_open_order must always be available")
    if by_key["submit_approved_intent"]["risk_class"] != "R3":
        problems.append("submit_approved_intent must be R3 example")

    features = promotion["features"]
    if features["raw_order_cli"]["V3_PAPER"] is not False:
        problems.append("raw_order_cli must be forbidden in V3")
    if features["auto_approve_submit"]["V3_PAPER"] is not False:
        problems.append("auto approve/submit must be out of scope")
    return problems


def main() -> int:
    problems = validate()
    if problems:
        print("4장 계약 위반:")
        for p in problems:
            print(" -", p)
        return 1
    print("4장 Console V2·V3 계약 검사 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
