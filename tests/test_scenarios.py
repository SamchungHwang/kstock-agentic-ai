from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kstock.audit_store import trace
from kstock.console_commands import COMMANDS
from kstock.console_runner import CommandRunner, validate_result_contract
from kstock.demo_services import (
    account_query,
    cancel_open_orders,
    dart_collect,
    dart_replay,
    full_check,
    halt_trading,
    inject_audit_failure,
    inject_quote_mode,
    inject_reconciliation_mode,
    open_gate,
    order_submit_out_of_scope,
    quick_check,
    quote_query,
    reconcile,
    resume_trading,
    seed_open_order,
    seed_unknown_order,
    start_console_session,
)
from kstock.models import CommandContext, ResultStatus
from kstock.state_store import external_call_counts, read_state, update_state


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("KSTOCK_CONSOLE_DATA", str(tmp_path / "data"))


def prepare_initial_openable_state() -> None:
    assert reconcile("corr_recon").status is ResultStatus.SUCCESS
    assert full_check("corr_full").status is ResultStatus.SUCCESS


def prepare_halted_recoverable_state() -> None:
    prepare_initial_openable_state()
    assert open_gate("corr_open", "START TRADING").status is ResultStatus.SUCCESS
    assert halt_trading("corr_halt", "시험 정지").status is ResultStatus.SUCCESS
    assert reconcile("corr_recon_after_halt").status is ResultStatus.SUCCESS
    assert full_check("corr_full_after_halt").status is ResultStatus.SUCCESS


def test_01_program_start_never_reuses_open_gate():
    update_state(lambda s: s["gate"].update({"state": "OPEN"}))
    result = start_console_session("corr_session")
    assert result.status is ResultStatus.SUCCESS
    assert read_state()["gate"]["state"] == "CLOSED"


def test_02_quick_check_never_calls_external_boundary():
    before = external_call_counts()
    quick_check("corr_quick")
    after = external_call_counts()
    assert after == before


def test_03_full_check_calls_demo_external_boundary_only_when_explicit():
    before = external_call_counts()
    read_state()  # 로컬 자동 갱신과 같은 동작
    quick_check("corr_quick")
    assert external_call_counts() == before
    reconcile("corr_recon")
    before_full = external_call_counts()
    full_check("corr_full")
    after_full = external_call_counts()
    assert sum(after_full.values()) > sum(before_full.values())


def test_04_mismatch_blocks_gate_open():
    inject_reconciliation_mode("corr_mode", "MISMATCH")
    result = reconcile("corr_mismatch")
    assert result.status is ResultStatus.BLOCKED
    opened = open_gate("corr_open", "START TRADING")
    assert opened.status is ResultStatus.BLOCKED
    assert read_state()["gate"]["state"] == "HALTED"


def test_05_unknown_reconciliation_is_not_treated_as_normal():
    inject_reconciliation_mode("corr_mode", "UNKNOWN")
    result = reconcile("corr_unknown")
    assert result.status is ResultStatus.UNKNOWN
    opened = open_gate("corr_open", "START TRADING")
    assert opened.status is ResultStatus.BLOCKED
    assert opened.code == "RECONCILIATION_NOT_MATCH"


def test_06_start_trading_phrase_must_match_exactly():
    prepare_initial_openable_state()
    result = open_gate("corr_open", "start trading")
    assert result.status is ResultStatus.BLOCKED
    assert result.code == "CONFIRMATION_MISMATCH"


def test_07_resume_requires_phrase_and_current_recovery_checks():
    prepare_halted_recoverable_state()
    wrong = resume_trading("corr_resume_bad", "RESUME", "복구 완료")
    assert wrong.status is ResultStatus.BLOCKED
    ok = resume_trading(
        "corr_resume_ok",
        "RESUME TRADING",
        "대사와 전체 점검 완료",
    )
    assert ok.status is ResultStatus.SUCCESS
    assert read_state()["gate"]["state"] == "OPEN"


class _FakeTk:
    @staticmethod
    def after(_delay, callback, *args):
        callback(*args)


def test_08_emergency_command_can_be_acquired_during_other_work():
    runner = CommandRunner(_FakeTk())
    assert runner.try_acquire(COMMANDS["full_check"]) is True
    assert runner.try_acquire(COMMANDS["halt"]) is True
    runner.release(COMMANDS["full_check"])


def test_09_query_reconcile_and_cancel_work_while_halted():
    seed_open_order("corr_seed")
    halt_trading("corr_halt", "시험 정지")
    assert account_query("corr_account").status is ResultStatus.SUCCESS
    assert reconcile("corr_recon").status is ResultStatus.SUCCESS
    canceled = cancel_open_orders("corr_cancel", "CONFIRM")
    assert canceled.status is ResultStatus.SUCCESS
    assert canceled.payload["canceled_order_ids"]
    assert read_state()["gate"]["state"] == "HALTED"


def test_10_console_v1_explicitly_has_no_order_submit_path():
    result = order_submit_out_of_scope("corr_submit")
    assert result.status is ResultStatus.BLOCKED
    assert result.code == "OUT_OF_SCOPE_CONSOLE_V1"
    assert result.payload["order_submitted"] is False
    assert result.payload["automatic_retry"] is False


def test_11_dart_replay_never_calls_external_boundary():
    dart_collect("corr_collect")
    before = external_call_counts()
    replay = dart_replay("corr_replay")
    after = external_call_counts()
    assert replay.status is ResultStatus.SUCCESS
    assert replay.payload["network_called"] is False
    assert after == before


def test_12_same_saved_dart_batch_has_same_normalized_hash():
    dart_collect("corr_collect")
    a = dart_replay("corr_replay_a")
    b = dart_replay("corr_replay_b")
    assert a.payload["normalized_hash"] == b.payload["normalized_hash"]
    assert a.payload["normalized"] == b.payload["normalized"]


def test_13_duplicate_query_lock_group_is_rejected():
    runner = CommandRunner(_FakeTk())
    assert runner.try_acquire(COMMANDS["account_query"]) is True
    assert runner.try_acquire(COMMANDS["quote_query"]) is False
    runner.release(COMMANDS["account_query"])


def test_14_local_state_refresh_does_not_call_external_boundary():
    before = external_call_counts()
    for _ in range(5):
        read_state()
    assert external_call_counts() == before


def test_15_json_and_exit_code_mismatch_is_contract_error():
    event = {
        "kind": "result",
        "status": "SUCCESS",
        "code": "OK",
        "message": "ok",
        "correlation_id": "corr_contract",
        "payload": {},
    }
    checked = validate_result_contract(event, 1, "corr_contract")
    assert checked["status"] == "ERROR"
    assert checked["code"] == "CLI_CONTRACT_MISMATCH"


def test_16_all_registered_commands_include_correlation_id():
    for spec in COMMANDS.values():
        ctx = CommandContext("PAPER", "corr_all", {})
        argv = spec.argv(ctx, [sys.executable, "-m", "kstock.console_v1_cli"])
        index = argv.index("--correlation-id")
        assert argv[index + 1] == "corr_all"


def test_17_reconciliation_halt_flow_uses_same_correlation_id():
    inject_reconciliation_mode("corr_mode", "MISMATCH")
    correlation_id = "corr_reconciliation_flow"
    reconcile(correlation_id)
    events = trace(correlation_id)
    names = [event["event"] for event in events]
    assert "RECONCILIATION" in names
    assert "KILL_SWITCH_CHANGED" in names
    assert "GATE_CHANGED" in names


def test_18_audit_write_failure_blocks_new_risk_and_resume():
    prepare_initial_openable_state()
    inject_audit_failure("corr_fail", True)
    blocked = open_gate("corr_open", "START TRADING")
    assert blocked.status is ResultStatus.BLOCKED
    assert read_state()["gate"]["state"] == "CLOSED"

    inject_audit_failure("corr_fix", False)
    assert open_gate("corr_open2", "START TRADING").status is ResultStatus.SUCCESS
    halt_trading("corr_halt", "시험 정지")
    reconcile("corr_recon_after")
    full_check("corr_full_after")
    inject_audit_failure("corr_fail2", True)
    resumed = resume_trading(
        "corr_resume",
        "RESUME TRADING",
        "복구 완료",
    )
    assert resumed.status is ResultStatus.BLOCKED
    assert read_state()["gate"]["state"] == "HALTED"


def test_19_suspended_quote_does_not_present_last_price_as_live_mark():
    inject_quote_mode("corr_mode", "SUSPENDED")
    result = quote_query("corr_quote", "005930")
    assert result.status is ResultStatus.SUCCESS
    assert result.payload["price_state"] == "STALE"
    assert result.payload["risk_price"] != result.payload["display_price"]
    assert result.payload["risk_valuation_reason"] == "SUSPENDED_HAIRCUT"


def test_20_resume_rereads_latest_authoritative_state():
    prepare_halted_recoverable_state()
    # 전체 점검 이후 권위 상태에 UNKNOWN 주문을 추가한다.
    seed_unknown_order("corr_unknown_order")
    result = resume_trading(
        "corr_resume",
        "RESUME TRADING",
        "GUI에는 정상으로 보였지만 최신 상태를 재검사",
    )
    assert result.status is ResultStatus.BLOCKED
    assert result.code == "UNKNOWN_ORDERS"
    assert read_state()["gate"]["state"] == "HALTED"
