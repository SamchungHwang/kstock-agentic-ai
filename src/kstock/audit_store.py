from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state_store import data_dir, file_lock, now_iso


def audit_path() -> Path:
    return data_dir() / "audit.jsonl"


def failure_marker_path() -> Path:
    return data_dir() / ".audit_write_failure"


def set_failure_injection(enabled: bool) -> None:
    """시험 전용 감사 저장 실패 주입."""
    marker = failure_marker_path()
    if enabled:
        marker.write_text("simulated audit write failure\n", encoding="utf-8")
    else:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass


def _raise_if_injected() -> None:
    if failure_marker_path().exists():
        raise OSError("시험용 감사 로그 쓰기 실패가 활성화돼 있습니다.")


def probe_writable() -> None:
    """감사 로그가 실제로 append 가능한지 상태 변경 전에 확인한다."""
    _raise_if_injected()
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock():
        with path.open("a", encoding="utf-8") as stream:
            stream.flush()


def append_audit(
    *,
    event: str,
    status: str,
    correlation_id: str,
    actor: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _raise_if_injected()
    record = {
        "timestamp": now_iso(),
        "event": event,
        "status": status,
        "actor": actor,
        "message": message,
        "correlation_id": correlation_id,
        "payload": payload or {},
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with file_lock():
        with audit_path().open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
    return record


def read_recent(limit: int = 100) -> list[dict[str, Any]]:
    path = audit_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({
                "timestamp": "",
                "event": "AUDIT_PARSE_ERROR",
                "status": "ERROR",
                "actor": "audit_store",
                "message": line[:120],
                "correlation_id": "",
                "payload": {},
            })
    return records[-limit:]


def trace(correlation_id: str) -> list[dict[str, Any]]:
    return [
        item for item in read_recent(limit=5000)
        if item.get("correlation_id") == correlation_id
    ]


def health(*, check_write: bool = True) -> tuple[str, str]:
    try:
        records = read_recent(limit=20)
        parse_errors = sum(
            1 for item in records
            if item.get("event") == "AUDIT_PARSE_ERROR"
        )
        if check_write:
            probe_writable()
        if parse_errors:
            return "DEGRADED", f"최근 로그에 파싱 오류 {parse_errors}건"
        return "HEALTHY", f"최근 감사 기록 {len(records)}건 읽기·쓰기 정상"
    except OSError as exc:
        return "UNHEALTHY", str(exc)
