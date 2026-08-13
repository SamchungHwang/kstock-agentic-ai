from __future__ import annotations

from pathlib import Path

import pytest

from kstock.fixed_identity import (
    OWNER_ACTOR_ID,
    assert_fixed_account_binding,
    fixed_account_ref,
)
from kstock.state_store import (
    configure_runtime_environment,
    read_state,
    state_path,
    update_state,
)


def test_single_human_owner_id_is_fixed() -> None:
    assert OWNER_ACTOR_ID == "OWNER"


def test_environment_selects_exactly_one_fixed_account() -> None:
    assert fixed_account_ref("PAPER").value == "PAPER_PRIMARY"
    assert fixed_account_ref("LIVE").value == "LIVE_PRIMARY"


def test_wrong_environment_account_binding_is_rejected() -> None:
    with pytest.raises(ValueError, match="fixed account binding mismatch"):
        assert_fixed_account_binding("LIVE", "PAPER_PRIMARY")


def test_paper_and_live_runtime_state_are_physically_isolated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KSTOCK_CONSOLE_DATA", str(tmp_path / "data"))

    configure_runtime_environment("PAPER")
    update_state(lambda state: state["gate"].update({"state": "OPEN"}))
    paper_path = state_path()
    assert read_state()["account_ref"] == "PAPER_PRIMARY"
    assert read_state()["gate"]["state"] == "OPEN"

    configure_runtime_environment("LIVE")
    live_path = state_path()
    assert live_path != paper_path
    assert read_state()["account_ref"] == "LIVE_PRIMARY"
    assert read_state()["gate"]["state"] == "CLOSED"

    configure_runtime_environment("PAPER")
    assert read_state()["gate"]["state"] == "OPEN"


def test_service_layer_rejects_in_process_environment_switch(tmp_path: Path, monkeypatch) -> None:
    from kstock.demo_services import account_query

    monkeypatch.setenv("KSTOCK_CONSOLE_DATA", str(tmp_path / "data"))
    configure_runtime_environment("PAPER")
    with pytest.raises(RuntimeError, match="RUNTIME_ENVIRONMENT_SWITCH_FORBIDDEN"):
        account_query("corr_wrong_env", "LIVE")


def test_execution_world_rejects_wrong_account_for_environment() -> None:
    from kstock.execution_world import Account, Environment, Order

    with pytest.raises(ValueError, match="fixed account binding mismatch"):
        Account(account_ref="LIVE_PRIMARY", environment=Environment.PAPER)

    with pytest.raises(ValueError, match="fixed account binding mismatch"):
        Order(
            order_id="ord_wrong",
            intent_id="intent_wrong",
            account_ref="PAPER_PRIMARY",
            security_id="sec_005930",
            environment=Environment.LIVE,
        )
