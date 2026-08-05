from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable

from .console_commands import CommandSpec, default_runner, source_root
from .models import CommandContext, EXIT_CODE_BY_STATUS, ResultStatus


@dataclass
class RunCallbacks:
    on_progress: Callable[[dict], None]
    on_stderr: Callable[[str], None]
    on_complete: Callable[[dict], None]


def validate_result_contract(
    final_event: dict | None,
    return_code: int,
    correlation_id: str,
) -> dict:
    """JSON 최종 결과와 프로세스 종료 코드의 계약을 교차 확인한다."""
    if final_event is None:
        return {
            "kind": "result",
            "status": "ERROR",
            "code": "MISSING_RESULT_EVENT",
            "message": "CLI가 최종 result 이벤트를 반환하지 않았습니다.",
            "correlation_id": correlation_id,
            "payload": {},
        }
    try:
        status = ResultStatus(final_event["status"])
        expected = EXIT_CODE_BY_STATUS[status]
        if return_code != expected:
            return {
                "kind": "result",
                "status": "ERROR",
                "code": "CLI_CONTRACT_MISMATCH",
                "message": (
                    f"JSON status={status.value}, exit={return_code}, "
                    f"expected={expected}"
                ),
                "correlation_id": correlation_id,
                "payload": {"original_result": final_event},
            }
        return final_event
    except Exception as exc:
        return {
            "kind": "result",
            "status": "ERROR",
            "code": "INVALID_RESULT_EVENT",
            "message": str(exc),
            "correlation_id": correlation_id,
            "payload": {"original_result": final_event},
        }


class CommandRunner:
    """검증된 argv를 shell=False로 실행하고 JSONL 계약을 확인한다."""

    def __init__(self, tk_root) -> None:
        self.tk_root = tk_root
        self._active_groups: set[str] = set()
        self._guard = threading.Lock()

    def group_active(self, group: str) -> bool:
        with self._guard:
            return group in self._active_groups

    def try_acquire(self, spec: CommandSpec) -> bool:
        group = spec.lock_group.value
        with self._guard:
            if group in self._active_groups and not spec.always_available:
                return False
            if not spec.always_available:
                self._active_groups.add(group)
            return True

    def release(self, spec: CommandSpec) -> None:
        if spec.always_available:
            return
        with self._guard:
            self._active_groups.discard(spec.lock_group.value)

    def run(
        self,
        spec: CommandSpec,
        ctx: CommandContext,
        callbacks: RunCallbacks,
    ) -> bool:
        if not self.try_acquire(spec):
            callbacks.on_complete({
                "kind": "result",
                "status": "BLOCKED",
                "code": "LOCK_GROUP_BUSY",
                "message": f"{spec.lock_group.value} 작업이 이미 실행 중입니다.",
                "correlation_id": ctx.correlation_id,
                "payload": {},
            })
            return False

        argv = spec.argv(ctx, default_runner())
        env = os.environ.copy()
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(source_root()) + (
            os.pathsep + current if current else ""
        )
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        def worker() -> None:
            final_event: dict | None = None
            stderr_lines: list[str] = []
            return_code = 1
            try:
                process = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    shell=False,
                    env=env,
                )
                assert process.stdout is not None
                assert process.stderr is not None

                stderr_queue: queue.Queue[str | None] = queue.Queue()

                def read_stderr() -> None:
                    for line in process.stderr:
                        stderr_queue.put(line.rstrip("\n"))
                    stderr_queue.put(None)

                stderr_thread = threading.Thread(
                    target=read_stderr,
                    daemon=True,
                )
                stderr_thread.start()

                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        stderr_lines.append("stdout JSON 파싱 실패: " + line)
                        continue
                    if event.get("kind") == "progress":
                        self.tk_root.after(0, callbacks.on_progress, event)
                    elif event.get("kind") == "result":
                        final_event = event

                return_code = process.wait()
                stderr_thread.join(timeout=2.0)
                while True:
                    try:
                        item = stderr_queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        break
                    stderr_lines.append(item)

                final_event = validate_result_contract(
                    final_event,
                    return_code,
                    ctx.correlation_id,
                )
            except Exception as exc:
                final_event = {
                    "kind": "result",
                    "status": "ERROR",
                    "code": "PROCESS_START_ERROR",
                    "message": str(exc),
                    "correlation_id": ctx.correlation_id,
                    "payload": {},
                }
            finally:
                self.release(spec)
                for line in stderr_lines:
                    self.tk_root.after(0, callbacks.on_stderr, line)
                assert final_event is not None
                self.tk_root.after(0, callbacks.on_complete, final_event)

        threading.Thread(target=worker, daemon=True).start()
        return True
