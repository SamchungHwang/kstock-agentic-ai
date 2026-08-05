from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CLI_LAUNCHER = ROOT / "run_cli.py"


def run_cli(tmp_path: Path, *args: str, correlation_id: str = "corr_test"):
    env = os.environ.copy()
    # 다른 프로젝트나 가상환경의 PYTHONPATH를 지우지 않고 앞에 붙인다.
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + current if current else "")
    env["KSTOCK_CONSOLE_DATA"] = str(tmp_path / "data")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["KIS_PAPER_APP_KEY"] = "test-paper-app-key"
    env["KIS_PAPER_APP_SECRET"] = "test-paper-app-secret"
    env["KIS_PAPER_ACCOUNT"] = "50012345-01"
    env["KIS_PAPER_ACCOUNT_PRODUCT"] = "01"
    command = [
        sys.executable,
        str(CLI_LAUNCHER),
        *args,
        "--environment",
        "PAPER",
        "--correlation-id",
        correlation_id,
        "--output",
        "jsonl",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        # 테스트 임시 폴더에서 실행해도 프로젝트 CLI가 정확히 선택돼야 한다.
        cwd=tmp_path,
    )
    events = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]
    return completed, events


def final(events):
    return [item for item in events if item.get("kind") == "result"][-1]


def test_cli_launcher_resolves_project_source(tmp_path):
    completed, events = run_cli(tmp_path, "startup", "session-init")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert final(events)["code"] == "CONSOLE_SESSION_STARTED"


def test_cli_safe_startup_flow(tmp_path):
    completed, events = run_cli(tmp_path, "startup", "session-init")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert final(events)["code"] == "CONSOLE_SESSION_STARTED"

    completed, events = run_cli(tmp_path, "reconcile", "run")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    completed, events = run_cli(tmp_path, "startup", "full-check")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    completed, events = run_cli(
        tmp_path,
        "gate",
        "open",
        "--confirmation",
        "START TRADING",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert final(events)["code"] == "GATE_OPENED"


def test_cli_order_submit_is_explicitly_out_of_scope(tmp_path):
    completed, events = run_cli(tmp_path, "order", "submit")
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert final(events)["code"] == "OUT_OF_SCOPE_CONSOLE_V1"


def test_launcher_does_not_import_existing_kstock_cli_package(tmp_path):
    """프로젝트에 kstock/cli 패키지가 있어도 Console V1 전용 모듈을 실행한다."""
    completed, events = run_cli(tmp_path, "startup", "session-init")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert final(events)["code"] == "CONSOLE_SESSION_STARTED"
