from __future__ import annotations

import json
import sys
from typing import Any

from .models import EXIT_CODE_BY_STATUS, ResultStatus


def force_utf8_stdio() -> None:
    """Windows를 포함해 CLI stdout/stderr를 UTF-8로 고정한다.

    stdout의 JSONL은 추가로 ensure_ascii=True를 사용하므로, 부모 프로세스가
    어떤 로캘에서 실행돼도 한글 메시지가 깨지지 않는다.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                # 이미 닫혔거나 재설정할 수 없는 스트림이면 기존 설정을 사용한다.
                pass


class JsonlEmitter:
    def __init__(self, correlation_id: str) -> None:
        self.correlation_id = correlation_id

    def _emit(self, body: dict[str, Any]) -> None:
        body.setdefault("correlation_id", self.correlation_id)
        # CLI와 GUI 사이의 wire format은 ASCII-safe JSON으로 보낸다.
        # json.loads() 후에는 원래 한글 문자열로 복원된다.
        print(
            json.dumps(
                body,
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            flush=True,
        )

    def progress(
        self,
        step: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._emit({
            "kind": "progress",
            "step": step,
            "message": message,
            "payload": payload or {},
        })

    def result(
        self,
        status: ResultStatus,
        code: str,
        message: str,
        payload: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> int:
        body: dict[str, Any] = {
            "kind": "result",
            "status": status.value,
            "code": code,
            "message": message,
            "payload": payload or {},
        }
        if next_action:
            body["next_action"] = next_action
        self._emit(body)
        return EXIT_CODE_BY_STATUS[status]


def diagnostic(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
