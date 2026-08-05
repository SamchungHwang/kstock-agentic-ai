"""Headless-checkable Tkinter console skeleton. Never import kstock here."""
from __future__ import annotations
import argparse
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Sequence
import uuid

from console_commands import (
    CommandContext, Environment, RiskClass, build_registry,
    command_manifest, status_from_exit_code, visible_specs,
)

class Worker:
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        self.events = events
        self.process: subprocess.Popen[str] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, key: str, argv: Sequence[str]) -> None:
        if self.running:
            raise RuntimeError("worker is already running")
        kwargs: dict[str, object] = {
            "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL, "text": True,
            "encoding": "utf-8", "errors": "replace", "shell": False,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(list(argv), **kwargs)
        assert self.process.stdout and self.process.stderr
        threading.Thread(target=self._read, args=(key, "stdout", self.process.stdout), daemon=True).start()
        threading.Thread(target=self._read, args=(key, "stderr", self.process.stderr), daemon=True).start()
        threading.Thread(target=self._wait, args=(key, self.process), daemon=True).start()

    def _read(self, key: str, source: str, stream: object) -> None:
        for line in stream:  # type: ignore[union-attr]
            self.events.put(("stream", (key, source, line.rstrip())))

    def _wait(self, key: str, process: subprocess.Popen[str]) -> None:
        self.events.put(("finished", (key, process.wait())))

class ConsoleApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.registry = build_registry()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.general_worker = Worker(self.events)
        self.control_worker = Worker(self.events)
        self.buttons: dict[str, ttk.Button] = {}
        self.environment = tk.StringVar(value="PAPER")
        self.account_alias = tk.StringVar(value="paper-main")
        self.status = tk.StringVar(value="○ 대기")
        self.grid(sticky="nsew")
        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        self.master.title("K-Stock Console [PAPER]")
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="환경").pack(side="left")
        ttk.Combobox(header, textvariable=self.environment, values=["PAPER", "LIVE"], state="readonly", width=8).pack(side="left", padx=6)
        ttk.Label(header, text="계좌 별칭").pack(side="left")
        ttk.Entry(header, textvariable=self.account_alias, width=18).pack(side="left", padx=6)
        ttk.Label(header, textvariable=self.status).pack(side="right")
        controls = ttk.LabelFrame(self, text="Console V1 명령")
        controls.grid(row=1, column=0, sticky="ew", pady=8)
        for i, spec in enumerate(visible_specs(self.registry)):
            button = ttk.Button(controls, text=spec.label, command=lambda key=spec.key: self._request(key))
            button.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="ew")
            self.buttons[spec.key] = button
        frame = ttk.LabelFrame(self, text="실행 로그")
        frame.grid(row=2, column=0, sticky="nsew")
        self.log = tk.Text(frame, width=100, height=24, state="disabled")
        self.log.pack(fill="both", expand=True)

    def _request(self, key: str) -> None:
        spec = self.registry[key]
        reason = ""
        if spec.risk_class is RiskClass.CONTROL:
            reason = simpledialog.askstring("통제 사유", "사유를 입력하십시오.", parent=self.master) or ""
            if not reason.strip():
                return
        try:
            ctx = CommandContext(
                environment=Environment(self.environment.get()),
                correlation_id=f"corr_{uuid.uuid4().hex[:12]}",
                account_alias=self.account_alias.get().strip(), reason=reason,
            )
            argv = spec.argv(ctx, [sys.executable, "-m", "kstock.cli"])
            worker = self.control_worker if spec.always_available else self.general_worker
            worker.start(key, argv)
        except Exception as exc:
            messagebox.showerror("명령 시작 실패", str(exc), parent=self.master)
            return
        self.status.set("⏳ 실행")
        if not spec.always_available:
            self._set_general(False)
        self._append(f"$ {argv!r}")

    def _set_general(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for key, button in self.buttons.items():
            button.configure(state="normal" if self.registry[key].always_available else state)

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "stream":
                key, source, text = payload  # type: ignore[misc]
                self._append(f"[{key}:{source}] {text}")
            else:
                key, code = payload  # type: ignore[misc]
                status = status_from_exit_code(code)
                icon = "✓" if status.value == "SUCCESS" else "!" if status.value == "BLOCKED" else "✗"
                self.status.set(f"{icon} {status.value}")
                self._append(f"[{key}] exit={code} status={status.value}")
                if not self.registry[key].always_available:
                    self._set_general(True)
        self.after(100, self._poll)

    def _append(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", dest="print_manifest", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)

def run_check() -> int:
    registry = build_registry()
    failures: list[str] = []
    if not registry:
        failures.append("registry is empty")
    if any(s.risk_class is RiskClass.ECONOMIC for s in registry.values()):
        failures.append("Console V1 contains ECONOMIC command")
    if not any(s.always_available for s in registry.values()):
        failures.append("always-available control command is missing")
    ctx = CommandContext(Environment.PAPER, "corr_check", "paper-main", "headless check")
    for spec in visible_specs(registry):
        try:
            argv = spec.argv(ctx, [sys.executable, "-m", "kstock.cli"])
            if not isinstance(argv, list) or "--environment" not in argv or "--correlation-id" not in argv:
                failures.append(f"{spec.key}: invalid argv")
        except Exception as exc:
            failures.append(f"{spec.key}: {exc}")
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    print(f"OK: {len(registry)} implemented commands; Console V1 contains no economic command")
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_manifest:
        print(json.dumps(command_manifest(build_registry()), ensure_ascii=False, indent=2))
        return 0
    if args.check:
        return run_check()
    root = tk.Tk()
    ConsoleApp(root)
    root.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
