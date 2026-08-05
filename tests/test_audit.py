from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kstock.audit_store import append_audit, health, trace


def test_correlation_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("KSTOCK_CONSOLE_DATA", str(tmp_path / "data"))
    append_audit(
        event="TEST_A",
        status="SUCCESS",
        correlation_id="corr_same",
        actor="test",
        message="a",
    )
    append_audit(
        event="TEST_B",
        status="SUCCESS",
        correlation_id="corr_same",
        actor="test",
        message="b",
    )
    assert [item["event"] for item in trace("corr_same")] == [
        "TEST_A",
        "TEST_B",
    ]
    status, _ = health()
    assert status == "HEALTHY"
