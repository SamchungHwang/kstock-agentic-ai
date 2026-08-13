from __future__ import annotations

import argparse
import json
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext, ttk
from uuid import uuid4

from .console_commands import COMMANDS, CommandSpec
from .console_runner import CommandRunner, RunCallbacks
from .demo_services import start_console_session
from .fixed_identity import OWNER_ACTOR_ID, fixed_account_ref, normalize_environment
from .models import CommandContext
from .state_store import configure_runtime_environment, read_state


STATUS_MARK = {
    "SUCCESS": "✓",
    "BLOCKED": "!",
    "ERROR": "✗",
    "UNKNOWN": "✗",
}


def new_correlation_id() -> str:
    return "corr_" + uuid4().hex[:12]


class TypedConfirmationDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        title: str,
        phrase: str,
        summary: str,
        ask_reason: bool = False,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(
            self,
            text=summary,
            justify="left",
            wraplength=460,
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            padx=18,
            pady=(18, 10),
            sticky="w",
        )
        ttk.Label(self, text=f"확인 문구: {phrase}").grid(
            row=1,
            column=0,
            columnspan=2,
            padx=18,
            pady=5,
            sticky="w",
        )
        self.confirmation = ttk.Entry(self, width=46)
        self.confirmation.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=18,
            pady=5,
        )
        self.reason = None
        row = 3
        if ask_reason:
            ttk.Label(self, text="사유").grid(
                row=row,
                column=0,
                columnspan=2,
                padx=18,
                pady=(8, 2),
                sticky="w",
            )
            row += 1
            self.reason = ttk.Entry(self, width=46)
            self.reason.grid(
                row=row,
                column=0,
                columnspan=2,
                padx=18,
                pady=5,
            )
            row += 1
        ttk.Button(self, text="취소", command=self.destroy).grid(
            row=row,
            column=0,
            padx=8,
            pady=16,
            sticky="e",
        )
        ttk.Button(self, text="실행", command=self._submit).grid(
            row=row,
            column=1,
            padx=8,
            pady=16,
            sticky="w",
        )
        self.confirmation.focus_set()
        self.bind("<Return>", lambda _event: self._submit())
        self.wait_window(self)

    def _submit(self) -> None:
        self.result = {
            "confirmation": self.confirmation.get(),
            "reason": self.reason.get() if self.reason is not None else "",
        }
        self.destroy()


class ConsoleV1App(tk.Tk):
    LOCAL_REFRESH_MS = 1000

    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = normalize_environment(environment)
        self.account_ref = fixed_account_ref(self.environment).value
        self.title(f"K-Stock AI Agent — Console V1 [{self.environment}] {self.account_ref}")
        self.geometry("1280x860")
        self.minsize(1080, 720)
        self.runner = CommandRunner(self)
        self.status_var = tk.StringVar(value="○ 대기")
        self.gate_var = tk.StringVar(value="CLOSED")
        self.kill_var = tk.StringVar(value="OFF")
        self.recon_var = tk.StringVar(value="UNKNOWN")
        self.audit_var = tk.StringVar(value="UNKNOWN")
        self.last_result_var = tk.StringVar(value="아직 실행 결과가 없습니다.")
        self.buttons_by_group: dict[str, list[ttk.Button]] = {}
        self._build_ui()
        self.bind_all("<Control-l>", lambda _event: self._clear_screen_log())
        self.bind_all("<Control-L>", lambda _event: self._clear_screen_log())
        self.after(100, self.refresh_local_state)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        status = ttk.Frame(self, padding=8)
        status.grid(row=0, column=0, sticky="ew")
        for i in range(10):
            status.columnconfigure(i, weight=1)
        ttk.Label(
            status,
            text=f"{self.environment} · {self.account_ref}",
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(status, text="게이트").grid(row=0, column=1, sticky="e")
        ttk.Label(
            status,
            textvariable=self.gate_var,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=2, sticky="w", padx=5)
        ttk.Label(status, text="킬 스위치").grid(row=0, column=3, sticky="e")
        ttk.Label(
            status,
            textvariable=self.kill_var,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=4, sticky="w", padx=5)
        ttk.Label(status, text="대사").grid(row=0, column=5, sticky="e")
        ttk.Label(
            status,
            textvariable=self.recon_var,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=6, sticky="w", padx=5)
        ttk.Label(status, text="감사").grid(row=0, column=7, sticky="e")
        ttk.Label(
            status,
            textvariable=self.audit_var,
            font=("맑은 고딕", 10, "bold"),
        ).grid(row=0, column=8, sticky="w", padx=5)
        ttk.Label(status, textvariable=self.status_var).grid(
            row=0,
            column=9,
            sticky="e",
        )

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        tabs = ttk.Notebook(body)
        log_frame = ttk.Frame(body, padding=6)
        body.add(tabs, weight=3)
        body.add(log_frame, weight=2)

        startup = ttk.Frame(tabs, padding=12)
        query = ttk.Frame(tabs, padding=12)
        reconcile = ttk.Frame(tabs, padding=12)
        kill = ttk.Frame(tabs, padding=12)
        audit = ttk.Frame(tabs, padding=12)
        tabs.add(startup, text="안전 기동")
        tabs.add(query, text="조회")
        tabs.add(reconcile, text="대사")
        tabs.add(kill, text="킬 스위치")
        tabs.add(audit, text="감사 추적")

        self._build_startup_panel(startup)
        self._build_query_panel(query)
        self._build_reconcile_panel(reconcile)
        self._build_kill_panel(kill)
        self._build_audit_panel(audit)

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_header = ttk.Frame(log_frame)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        ttk.Label(
            log_header,
            text="실행 로그",
            font=("맑은 고딕", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            log_header,
            text="화면 로그 지우기",
            command=self._clear_screen_log,
        ).grid(row=0, column=1, sticky="e")

        self.log = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.log.grid(row=1, column=0, sticky="nsew", pady=6)
        ttk.Label(
            log_frame,
            textvariable=self.last_result_var,
            wraplength=450,
        ).grid(row=2, column=0, sticky="ew")

        emergency = tk.Frame(self, bg="#8b0000", padx=8, pady=8)
        emergency.grid(row=2, column=0, sticky="ew")
        emergency.columnconfigure(1, weight=1)
        tk.Label(
            emergency,
            text="비상",
            bg="#8b0000",
            fg="white",
            font=("맑은 고딕", 11, "bold"),
        ).grid(row=0, column=0, padx=8)
        self.halt_reason = tk.Entry(emergency)
        self.halt_reason.insert(0, "수동 비상 정지")
        self.halt_reason.grid(row=0, column=1, sticky="ew", padx=8)
        tk.Button(
            emergency,
            text="미체결 주문 취소",
            command=lambda: self.execute("cancel_open_orders", {}),
            bg="#fff2cc",
            fg="#7f6000",
            font=("맑은 고딕", 10, "bold"),
            padx=18,
        ).grid(row=0, column=2, padx=8)
        tk.Button(
            emergency,
            text="거래 정지",
            command=lambda: self.execute(
                "halt",
                {"reason": self.halt_reason.get()},
            ),
            bg="#ffdddd",
            fg="#8b0000",
            font=("맑은 고딕", 12, "bold"),
            padx=24,
        ).grid(row=0, column=3, padx=8)

    def _register_button(
        self,
        parent,
        command_key: str,
        row: int,
        column: int,
        values_factory=None,
        **grid,
    ) -> ttk.Button:
        spec = COMMANDS[command_key]
        button = ttk.Button(
            parent,
            text=spec.label,
            command=lambda: self.execute(
                command_key,
                values_factory() if values_factory else {},
            ),
        )
        button.grid(row=row, column=column, padx=5, pady=5, **grid)
        self.buttons_by_group.setdefault(spec.lock_group.value, []).append(button)
        return button

    def _build_startup_panel(self, frame) -> None:
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="안전 기동 콘솔",
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._register_button(frame, "quick_check", 1, 0, sticky="ew")
        self._register_button(frame, "full_check", 1, 1, sticky="ew")
        self._register_button(frame, "gate_status", 1, 2, sticky="ew")
        self._register_button(frame, "gate_open", 2, 0, sticky="ew")
        self._register_button(
            frame,
            "gate_close",
            2,
            1,
            lambda: {"reason": "Console V1에서 닫음"},
            sticky="ew",
        )
        ttk.Label(
            frame,
            text=(
                "게이트 열기는 최근 대사 MATCH, 최신 전체 점검 PASS, "
                "감사 로그 정상, START TRADING 확인이 필요합니다."
            ),
            wraplength=720,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=10)

    def _build_query_panel(self, frame) -> None:
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="조회 패널",
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._register_button(frame, "account_query", 1, 0, sticky="ew")
        self._register_button(
            frame,
            "quote_live",
            1,
            1,
            lambda: {"mode": "LIVE"},
            sticky="ew",
        )
        self._register_button(
            frame,
            "quote_suspended",
            1,
            2,
            lambda: {"mode": "SUSPENDED"},
            sticky="ew",
        )
        ttk.Label(frame, text="종목코드").grid(row=2, column=0, sticky="w")
        self.symbol_entry = ttk.Entry(frame)
        self.symbol_entry.insert(0, "005930")
        self.symbol_entry.grid(row=2, column=1, sticky="ew", padx=5)
        self._register_button(
            frame,
            "quote_query",
            2,
            2,
            lambda: {"symbol": self.symbol_entry.get()},
            sticky="ew",
        )
        ttk.Label(frame, text="지정가").grid(row=3, column=0, sticky="w")
        self.price_entry = ttk.Entry(frame)
        self.price_entry.insert(0, "82400")
        self.price_entry.grid(row=3, column=1, sticky="ew", padx=5)
        self._register_button(
            frame,
            "buying_power",
            3,
            2,
            lambda: {
                "symbol": self.symbol_entry.get(),
                "price": self.price_entry.get(),
            },
            sticky="ew",
        )
        self._register_button(frame, "dart_collect", 4, 0, sticky="ew")
        self._register_button(frame, "dart_replay", 4, 1, sticky="ew")
        ttk.Label(
            frame,
            text=(
                "외부 조회는 버튼으로만 실행합니다. 거래정지 시세 모드는 "
                "display_price와 risk_price가 분리되는지 시험합니다."
            ),
            wraplength=720,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=10)

    def _build_reconcile_panel(self, frame) -> None:
        ttk.Label(
            frame,
            text="대사 패널",
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._register_button(frame, "reconcile", 1, 0, sticky="ew")
        self._register_button(
            frame,
            "recon_match",
            1,
            1,
            lambda: {"mode": "MATCH"},
            sticky="ew",
        )
        self._register_button(
            frame,
            "recon_mismatch",
            1,
            2,
            lambda: {"mode": "MISMATCH"},
            sticky="ew",
        )
        self._register_button(
            frame,
            "recon_unknown",
            2,
            0,
            lambda: {"mode": "UNKNOWN"},
            sticky="ew",
        )
        self._register_button(frame, "repair_demo", 2, 1, sticky="ew")
        self._register_button(frame, "seed_open_order", 2, 2, sticky="ew")
        self._register_button(frame, "seed_unknown_order", 3, 0, sticky="ew")
        ttk.Label(
            frame,
            text=(
                "MISMATCH와 UNKNOWN은 모두 신규 위험을 차단합니다. "
                "UNKNOWN 주문은 게이트 열기와 재가동을 막습니다."
            ),
            wraplength=720,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=10)
        self.recon_detail = scrolledtext.ScrolledText(
            frame,
            height=15,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.recon_detail.grid(row=5, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_kill_panel(self, frame) -> None:
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="킬 스위치 패널",
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._register_button(frame, "kill_status", 1, 0, sticky="ew")
        ttk.Label(frame, text="재가동 사유").grid(row=2, column=0, sticky="w")
        self.resume_reason = ttk.Entry(frame)
        self.resume_reason.grid(row=2, column=1, sticky="ew", padx=5)
        self._register_button(
            frame,
            "resume",
            2,
            2,
            lambda: {"reason": self.resume_reason.get()},
            sticky="ew",
        )
        ttk.Label(
            frame,
            text=(
                "재가동 CLI는 GUI 표시값이 아니라 최신 로컬 권위 상태를 다시 읽고, "
                "대사·전체 점검·감사 건강도·UNKNOWN 주문을 재검사합니다."
            ),
            wraplength=720,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=10)
        self.kill_detail = scrolledtext.ScrolledText(
            frame,
            height=18,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.kill_detail.grid(row=4, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(4, weight=1)

    def _build_audit_panel(self, frame) -> None:
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="감사 추적 패널",
            font=("맑은 고딕", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._register_button(frame, "audit_health", 1, 0, sticky="ew")
        self._register_button(
            frame,
            "audit_recent",
            1,
            1,
            lambda: {"limit": 100},
            sticky="ew",
        )
        self._register_button(
            frame,
            "audit_fail_on",
            1,
            2,
            lambda: {"enabled": True},
            sticky="ew",
        )
        self._register_button(
            frame,
            "audit_fail_off",
            2,
            2,
            lambda: {"enabled": False},
            sticky="ew",
        )
        ttk.Label(frame, text="correlation_id").grid(row=2, column=0, sticky="w")
        self.trace_entry = ttk.Entry(frame)
        self.trace_entry.grid(row=2, column=1, sticky="ew", padx=5)
        self._register_button(
            frame,
            "audit_trace",
            3,
            2,
            lambda: {
                "target_correlation_id": self.trace_entry.get(),
            },
            sticky="ew",
        )
        self.audit_detail = scrolledtext.ScrolledText(
            frame,
            height=18,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.audit_detail.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(8, 0),
        )
        frame.rowconfigure(4, weight=1)

    def execute(self, command_key: str, values: dict) -> None:
        spec = COMMANDS[command_key]
        if spec.human_confirmation:
            phrase = spec.confirmation_phrase or "CONFIRM"
            ask_reason = command_key == "resume"
            summary = (
                f"{spec.label} 명령을 실행합니다.\n"
                f"환경: {self.environment}\n계좌: {self.account_ref}\n사용자: {OWNER_ACTOR_ID}\n필요 확인 문구: {phrase}"
            )
            dialog = TypedConfirmationDialog(
                self,
                spec.label,
                phrase,
                summary,
                ask_reason=ask_reason,
            )
            if dialog.result is None:
                return
            values = {**values, **dialog.result}

        corr = new_correlation_id()
        ctx = CommandContext(
            environment=self.environment,
            correlation_id=corr,
            values=values,
        )
        self.status_var.set(f"⏳ {spec.label}")
        self._append_log(
            f"\n[{datetime.now().strftime('%H:%M:%S')}] "
            f"{spec.label} 시작  {corr}"
        )
        if not spec.always_available:
            self._set_group_enabled(spec.lock_group.value, False)

        callbacks = RunCallbacks(
            on_progress=self._on_progress,
            on_stderr=self._on_stderr,
            on_complete=lambda event: self._on_complete(spec, event),
        )
        started = self.runner.run(spec, ctx, callbacks)
        if not started and not spec.always_available:
            self._set_group_enabled(spec.lock_group.value, True)

    def _on_progress(self, event: dict) -> None:
        self._append_log(f"  ⏳ {event.get('message', '')}")

    def _on_stderr(self, line: str) -> None:
        self._append_log("  [stderr] " + line)

    def _on_complete(self, spec: CommandSpec, event: dict) -> None:
        if not spec.always_available:
            self._set_group_enabled(spec.lock_group.value, True)
        status = event.get("status", "ERROR")
        mark = STATUS_MARK.get(status, "✗")
        message = event.get("message", "")
        code = event.get("code", "")
        corr = event.get("correlation_id", "")
        self.status_var.set(f"{mark} {status}")
        self.last_result_var.set(f"{mark} {message} [{code}] {corr}")
        self._append_log(f"  {mark} {status} {code}: {message}")
        payload = event.get("payload", {})
        if payload:
            self._append_log(json.dumps(payload, ensure_ascii=False, indent=2))
        if corr:
            self.trace_entry.delete(0, tk.END)
            self.trace_entry.insert(0, corr)
        if spec.key == "reconcile":
            self._write_text(
                self.recon_detail,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        elif spec.key == "kill_status":
            self._write_text(
                self.kill_detail,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        elif spec.key in {
            "audit_recent", "audit_trace", "audit_health",
            "audit_fail_on", "audit_fail_off",
        }:
            self._write_text(
                self.audit_detail,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        self.refresh_local_state()

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_screen_log(self) -> None:
        """화면 로그만 지우고 감사 로그와 correlation 이력은 유지한다."""
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self.last_result_var.set(
            "화면 로그를 지웠습니다. 감사 로그와 실행 이력은 유지됩니다."
        )
        self.status_var.set("○ 대기")

    @staticmethod
    def _write_text(widget, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state=tk.DISABLED)

    def _set_group_enabled(self, group: str, enabled: bool) -> None:
        for button in self.buttons_by_group.get(group, []):
            button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def refresh_local_state(self) -> None:
        """로컬 상태만 자동 갱신한다. 외부 경계 호출 금지."""
        try:
            state = read_state()
            self.gate_var.set(state["gate"]["state"])
            self.kill_var.set(state["kill_switch"]["state"])
            self.recon_var.set(state["last_reconciliation"]["status"])
            self.audit_var.set(state.get("audit_health", "UNKNOWN"))
        except Exception as exc:
            self.gate_var.set("UNKNOWN")
            self.kill_var.set("UNKNOWN")
            self.recon_var.set("UNKNOWN")
            self.audit_var.set("UNKNOWN")
            self.last_result_var.set(str(exc))
        self.after(self.LOCAL_REFRESH_MS, self.refresh_local_state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K-Stock Console V1")
    parser.add_argument("--environment", choices=["PAPER", "LIVE"], default="PAPER")
    args = parser.parse_args(argv)
    environment = configure_runtime_environment(args.environment)

    # GUI가 열리기 전에 해당 환경의 고정계좌 세션을 만들고 이전 OPEN 상태를 폐기한다.
    start_console_session(new_correlation_id(), environment)
    app = ConsoleV1App(environment)
    app.mainloop()
    return 0
