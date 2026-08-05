from __future__ import annotations
import sys
import pytest
from tools.console_commands import (
    CommandContext, ConfirmationState, Environment, ResultStatus,
    RiskClass, build_registry, confirmation_matches, status_from_exit_code,
)

def context() -> CommandContext:
    return CommandContext(Environment.PAPER, "corr_test", "paper-main", "test stop")

def test_v1_has_no_economic_command() -> None:
    assert all(s.risk_class is not RiskClass.ECONOMIC for s in build_registry().values())

def test_every_command_builds_argv_list() -> None:
    for spec in build_registry().values():
        argv = spec.argv(context(), [sys.executable, "-m", "kstock.cli"])
        assert isinstance(argv, list)
        assert "--environment" in argv
        assert "--correlation-id" in argv

def test_control_commands_are_always_available() -> None:
    controls = [s for s in build_registry().values() if s.risk_class is RiskClass.CONTROL]
    assert controls and all(s.always_available for s in controls)

def test_confirmation_is_never_prefilled() -> None:
    state = ConfirmationState("LIVE BUY 005930 24 82000")
    assert state.entered_phrase == ""
    assert not state.can_submit

def test_confirmation_requires_exact_manual_input() -> None:
    required = "LIVE BUY 005930 24 82000"
    assert confirmation_matches(required, required)
    assert not confirmation_matches(required, required + " ")
    assert not confirmation_matches(required, required.lower())

@pytest.mark.parametrize("code, expected", [
    (0, ResultStatus.SUCCESS), (10, ResultStatus.BLOCKED),
    (20, ResultStatus.ERROR), (50, ResultStatus.UNKNOWN),
    (130, ResultStatus.CANCELLED), (999, ResultStatus.ERROR),
])
def test_exit_code_contract(code: int, expected: ResultStatus) -> None:
    assert status_from_exit_code(code) is expected
