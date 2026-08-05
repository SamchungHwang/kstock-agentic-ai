from __future__ import annotations

import copy
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get("KSTOCK_CONSOLE_DATA")
    path = Path(override).expanduser().resolve() if override else project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


DEFAULT_STATE: dict[str, Any] = {
    "version": 3,
    "environment": "PAPER",
    "session": {
        "session_id": None,
        "started_at": None,
    },
    "gate": {
        "state": "CLOSED",
        "changed_at": None,
        "changed_by": "system",
        "reason": "초기 상태",
    },
    "kill_switch": {
        "state": "OFF",
        "changed_at": None,
        "changed_by": "system",
        "reason": "초기 상태",
    },
    "active_halt": None,
    "last_reconciliation": {
        "status": "UNKNOWN",
        "checked_at": None,
        "message": "아직 대사를 실행하지 않았습니다.",
        "differences": [],
    },
    "last_full_check": {
        "status": "UNKNOWN",
        "checked_at": None,
        "message": "아직 전체 점검을 실행하지 않았습니다.",
        "blockers": ["NOT_RUN"],
        "reconciliation_checked_at": None,
    },
    "audit_health": "UNKNOWN",
    "orders": [],
    "account_snapshot": None,
    "quote_snapshot": None,
    "buying_power_snapshot": None,
    "dart": {
        "last_collect": None,
        "saved_batches": [],
    },
    "metrics": {
        "external_calls": {},
    },
    "demo": {
        "reconciliation_mode": "MATCH",
        "quote_mode": "LIVE",
    },
}


class LockTimeout(RuntimeError):
    pass


@contextmanager
def file_lock(timeout: float = 3.0) -> Iterator[None]:
    lock_path = data_dir() / ".state.lock"
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LockTimeout(f"상태 파일 잠금 시간 초과: {lock_path}")
            time.sleep(0.03)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def state_path() -> Path:
    return data_dir() / "console_state.json"


def _deep_fill(current: Any, default: Any) -> Any:
    """기존 상태를 보존하면서 새 버전의 누락 필드를 채운다."""
    if isinstance(default, dict):
        base = current if isinstance(current, dict) else {}
        result = dict(base)
        for key, value in default.items():
            result[key] = _deep_fill(result.get(key), value)
        return result
    if isinstance(default, list):
        return current if isinstance(current, list) else copy.deepcopy(default)
    return default if current is None else current


def ensure_state() -> None:
    path = state_path()
    if not path.exists():
        with file_lock():
            if not path.exists():
                initial = copy.deepcopy(DEFAULT_STATE)
                initial["gate"]["changed_at"] = now_iso()
                initial["kill_switch"]["changed_at"] = now_iso()
                _write_unlocked(initial)
        return

    # 이전 실습 버전의 상태 파일도 읽을 수 있도록 느슨한 마이그레이션을 한다.
    with file_lock():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        merged = _deep_fill(current, DEFAULT_STATE)
        merged["version"] = DEFAULT_STATE["version"]
        if merged != current:
            _write_unlocked(merged)


def _write_unlocked(state: dict[str, Any]) -> None:
    path = state_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def read_state() -> dict[str, Any]:
    ensure_state()
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
        return _deep_fill(raw, DEFAULT_STATE)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"로컬 상태를 읽을 수 없습니다: {exc}") from exc


def update_state(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    ensure_state()
    with file_lock():
        state = _deep_fill(
            json.loads(state_path().read_text(encoding="utf-8")),
            DEFAULT_STATE,
        )
        mutator(state)
        state["version"] = DEFAULT_STATE["version"]
        _write_unlocked(state)
        return state


def external_call_counts() -> dict[str, int]:
    state = read_state()
    return {
        str(key): int(value)
        for key, value in state["metrics"].get("external_calls", {}).items()
    }
