from __future__ import annotations

import copy
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .fixed_identity import OWNER_ACTOR_ID, fixed_account_ref, normalize_environment


_RUNTIME_ENVIRONMENT = "PAPER"


def configure_runtime_environment(environment: str) -> str:
    """현재 프로세스가 다루는 실행 환경을 고정한다.

    한 CLI/GUI 프로세스는 PAPER 또는 LIVE 하나만 다룬다. GUI에서 환경을
    바꾸는 기능은 제공하지 않는다. 테스트와 별도 프로세스 진입점은 이 함수를
    시작 시 한 번 호출해 환경별 상태 저장소를 선택한다.
    """
    global _RUNTIME_ENVIRONMENT
    _RUNTIME_ENVIRONMENT = normalize_environment(environment)
    return _RUNTIME_ENVIRONMENT


def current_runtime_environment() -> str:
    return _RUNTIME_ENVIRONMENT


def require_runtime_environment(environment: str) -> str:
    """실행 중 환경 전환을 거부하고 현재 프로세스 환경과 일치하는지 확인한다."""
    requested = normalize_environment(environment)
    if requested != current_runtime_environment():
        raise RuntimeError(
            f"RUNTIME_ENVIRONMENT_SWITCH_FORBIDDEN: current={current_runtime_environment()}, "
            f"requested={requested}. 새 프로세스를 시작하십시오."
        )
    return requested


def current_account_ref() -> str:
    return fixed_account_ref(_RUNTIME_ENVIRONMENT).value


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    override = os.environ.get("KSTOCK_CONSOLE_DATA")
    path = Path(override).expanduser().resolve() if override else project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """PAPER/LIVE 상태·감사·저장본을 서로 다른 디렉터리에 둔다."""
    path = data_root() / current_runtime_environment().lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_state() -> dict[str, Any]:
    return {
        "version": 5,
        "environment": current_runtime_environment(),
        "account_ref": current_account_ref(),
        "owner_actor_id": OWNER_ACTOR_ID,
        # 7장에서 사용하는 단일 실행세계 통제 버전. 다계좌용 이중 버전은 쓰지 않는다.
        "control_version": 0,
        "session": {
            "session_id": None,
            "started_at": None,
        },
        "gate": {
            "state": "CLOSED",
            "changed_at": None,
            "changed_by": "SYSTEM",
            "reason": "초기 상태",
        },
        "kill_switch": {
            "state": "OFF",
            "changed_at": None,
            "changed_by": "SYSTEM",
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
        "interest_snapshot": None,
        "watch_universe": None,
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


def _enforce_fixed_identity(state: dict[str, Any]) -> None:
    state["environment"] = current_runtime_environment()
    state["account_ref"] = current_account_ref()
    state["owner_actor_id"] = OWNER_ACTOR_ID


def ensure_state() -> None:
    path = state_path()
    default = _default_state()
    if not path.exists():
        with file_lock():
            if not path.exists():
                initial = copy.deepcopy(default)
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
        # 이전 초안에서 사용한 control_epoch가 있으면 control_version으로 1회 마이그레이션한다.
        if "control_version" not in current and "control_epoch" in current:
            current["control_version"] = current.pop("control_epoch")
        merged = _deep_fill(current, default)
        merged["version"] = default["version"]
        _enforce_fixed_identity(merged)
        if merged != current:
            _write_unlocked(merged)


def _write_unlocked(state: dict[str, Any]) -> None:
    _enforce_fixed_identity(state)
    path = state_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def read_state() -> dict[str, Any]:
    ensure_state()
    default = _default_state()
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
        state = _deep_fill(raw, default)
        _enforce_fixed_identity(state)
        return state
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"로컬 상태를 읽을 수 없습니다: {exc}") from exc


def update_state(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    ensure_state()
    default = _default_state()
    with file_lock():
        state = _deep_fill(
            json.loads(state_path().read_text(encoding="utf-8")),
            default,
        )
        _enforce_fixed_identity(state)
        mutator(state)
        state["version"] = default["version"]
        _write_unlocked(state)
        return state


def external_call_counts() -> dict[str, int]:
    state = read_state()
    return {
        str(key): int(value)
        for key, value in state["metrics"].get("external_calls", {}).items()
    }
