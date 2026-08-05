from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kstock.console_commands import COMMANDS
from kstock.models import CommandContext


def test_safe_argv_is_list_and_contains_common_contract():
    spec = COMMANDS["quote_query"]
    ctx = CommandContext(
        "PAPER",
        "corr_test",
        {"symbol": "005930 | echo hacked"},
    )
    argv = spec.argv(ctx, ["python", "-m", "kstock.console_v1_cli"])
    assert isinstance(argv, list)
    assert "005930 | echo hacked" in argv
    assert "--environment" in argv
    assert "--correlation-id" in argv
    assert "--output" in argv


def test_emergency_commands_are_always_available():
    assert COMMANDS["halt"].always_available is True
    assert COMMANDS["cancel_open_orders"].always_available is True


def test_confirmation_phrases():
    assert COMMANDS["gate_open"].confirmation_phrase == "START TRADING"
    assert COMMANDS["resume"].confirmation_phrase == "RESUME TRADING"
    assert COMMANDS["repair_demo"].confirmation_phrase == "CONFIRM"
    assert COMMANDS["cancel_open_orders"].confirmation_phrase == "CONFIRM"
