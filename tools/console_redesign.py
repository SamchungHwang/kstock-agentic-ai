#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K-Stock AI Agent — 운영 콘솔 (UI 개편판).

    python tools/console.py            창
    python tools/console.py --print    명령 표만 출력
    python tools/console.py --flows    작업 흐름 출력
    python tools/console.py --check    명령 계약 검사

설계 원칙
----------
1. GUI는 kstock을 import하지 않는다.
2. 모든 업무 버튼은 기존 tools/*.py 명령을 subprocess로 실행한다.
3. 확인 문구는 사용자가 직접 입력하며 GUI가 자동 채우지 않는다.
4. 관심종목은 GUI 시작 시 tools/interest.py를 별도 프로세스로 호출하여
   .env 기반 KIS 관심종목을 동기화하고, watch_state를 다시 읽어 표시한다.
5. 관심종목 자동 동기화 실패 시에도 마지막 로컬 목록으로 콘솔은 열린다.

화면 구조
---------
┌ 환경·안전 상태 ─────────────────────────────── [거래 정지] ┐
├ 관심종목 ───┬ 오늘 할 일 / 작업 탭 ─────────┬ 선택 종목·확인 ┤
│ KIS 자동동기화│ 아침 열기 / 판단 / 주문 / 종료 │ 종목·수량·가격 │
│ 검색/목록     │ 버튼 + 설명                   │ 확인 문구       │
├─────────────┴───────────────────────────────┴───────────────┤
│ 실행 로그 / 흐름 추적                                         │
└──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from console_flows import FLOWS  # noqa: E402
from console_commands import (  # noqa: E402
    QUICK_LABELS,
    all_commands,
    confirm_hint,
    ticker_of,
    CONFIRM_HINTS,
    NOT_YET,
    SECTIONS,
    Command,
    check,
)
from console_state import format_line, format_second_line, read_safety  # noqa: E402

TITLE = "K-Stock AI Agent — 운영 콘솔"

# 명령의 inputs 이름과 맞춘다. UI에서는 필요한 항목만 전면에 노출한다.
FIELDS = (
    ("ticker", "종목", "", 10),
    ("quantity", "수량", "1", 7),
    ("price", "지정가", "", 10),
    ("order_id", "주문 id", "", 22),
    ("weight", "후보 비중", "", 8),
    ("why", "제외 사유", "", 20),
    ("confirm", "확인 문구", "", 30),
    ("thesis_id", "Thesis id", "", 18),
    ("corp_name", "회사명", "", 14),
    ("sample_path", "저장본", "", 26),
    ("pattern", "찾을 사건", "KILL", 16),
    ("correlation_id", "흐름 id", "", 28),
    ("actor", "사람", "owner", 10),
    ("reason", "사유", "", 28),
    ("trigger", "정지 원인", "MANUAL", 16),
    ("close_reason", "닫는 사유", "장 종료", 16),
)

FLAG_VALUES = {
    "price_flag": "--price",
    "reason_flag": "--reason",
    "why_flag": "--why",
    "confirm_flag": "--confirm",
    "dry_run_flag": "--dry-run",
    "weight_flag": "--weight",
}

COLORS = {
    "paper_bg": "#F3F8F3",
    "paper_accent": "#218838",
    "live_bg": "#FFF3F3",
    "live_accent": "#C0392B",
    "panel": "#FFFFFF",
    "panel_alt": "#F7F8FA",
    "line": "#D8DDE3",
    "text": "#1F2937",
    "muted": "#6B7280",
    "ok": "#218838",
    "warn": "#D97706",
    "red": "#C0392B",
    "blue": "#2563EB",
    "blue_soft": "#EFF6FF",
    "selected": "#E8F1FF",
}


# ---------------------------------------------------------------------------
# subprocess / 계약 헬퍼 (Tk 비의존)
# ---------------------------------------------------------------------------
def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def spawn(
    args: list[str],
    cwd: Path,
    on_line: Callable[[str], None],
    on_done: Callable[[int], None],
) -> threading.Thread:
    """[python, *args]를 실행하고 stdout을 줄 단위로 전달한다."""
    full = [sys.executable, *args]

    def quoted(value: str) -> str:
        return f'"{value}"' if " " in value else value

    def worker() -> None:
        on_line("$ " + " ".join(quoted(a) for a in args) + "\n")
        try:
            proc = subprocess.Popen(
                full,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=child_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:  # noqa: BLE001
            on_line(f"[실행 실패] {exc}\n")
            on_done(1)
            return
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            on_line(line)
        proc.stdout.close()
        rc = proc.wait()
        on_line(f"[종료코드 {rc}]\n\n")
        on_done(rc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def interest_sync_args(environment: str) -> list[str]:
    """GUI가 관심종목 동기화에 사용하는 유일한 명령 경로.

    GUI는 .env를 읽거나 KIS를 import하지 않는다. tools/interest.py가 담당한다.
    """
    return [
        str(TOOLS / "interest.py"),
        "--environment",
        environment.upper(),
        "--sync",
    ]


def interest_tool_available() -> bool:
    return (TOOLS / "interest.py").is_file()


def field_label(key: str) -> str:
    for name, label, _default, _width in FIELDS:
        if name == key:
            return label
    return key


def missing_hint(cmd: Command, values: dict[str, str]) -> str:
    for key in cmd.inputs:
        if key in FLAG_VALUES:
            continue
        if str(values.get(key, "")).strip():
            continue
        label = field_label(key)
        hint = confirm_hint(cmd.label, values)
        if hint is None or key != "confirm":
            return f"[입력 필요] {cmd.label}: '{label}'을 입력하십시오."
        _what, phrase = hint
        return (
            f"[확인 필요] {cmd.label}\n"
            f"    오른쪽 '확인 문구'에 아래 문구를 직접 입력하십시오.\n"
            f"    {phrase}\n"
        )
    return f"[입력 필요] {cmd.label}"


def mismatch_note(typed: str, values: dict[str, str]) -> str:
    typed_parts = typed.split()
    if not typed_parts:
        return ""
    best, best_score, best_label = None, -1, ""
    for label in CONFIRM_HINTS:
        hint = confirm_hint(label, values)
        if hint is None:
            continue
        parts = hint[1].split()
        if not parts:
            continue
        head = 2 if len(parts) == 2 else 1
        if parts[:head] != typed_parts[:head]:
            continue
        same = sum(1 for a, b in zip(parts, typed_parts) if a == b)
        if same > best_score:
            best, best_score, best_label = parts, same, label
    if best is None:
        return "현재 작업에 필요한 확인 문구와 일치하지 않습니다."
    names = {1: "종목", 2: "수량", 3: "가격"}
    for index, (want, got) in enumerate(zip(best, typed_parts)):
        if want == got:
            continue
        return f"{best_label}: {names.get(index, str(index + 1) + '번째 값')}이 다릅니다. ({want} / {got})"
    if len(best) != len(typed_parts):
        return f"{best_label}: 문구의 항목 수가 다릅니다."
    return "현재 작업에 필요한 확인 문구와 일치하지 않습니다."


def resolve_inputs(cmd: Command, values: dict[str, str]) -> list[str]:
    merged = dict(FLAG_VALUES)
    merged.update(values)
    if merged.get("ticker"):
        merged["ticker"] = ticker_of(merged["ticker"])
    if merged.get("order_id"):
        merged["order_id"] = order_id_of(merged["order_id"])
    return cmd.build(merged)


# ---------------------------------------------------------------------------
# watch_state 읽기 — GUI는 읽기만 한다
# ---------------------------------------------------------------------------
def watch_rows() -> list[tuple[str, str, str]]:
    """[(ticker, name, mark), ...]. 관심종목 + 보유종목 통합 view를 읽는다."""
    try:
        from watch_state import read_view

        rows: list[tuple[str, str, str]] = []
        for row in read_view().rows:
            ticker = str(getattr(row, "ticker", "")).strip()
            if not ticker:
                continue
            name = str(getattr(row, "name", "") or "").strip()
            mark = str(getattr(row, "mark", "") or "").strip()
            rows.append((ticker, name, mark))
        # 같은 종목이 보유/관심 양쪽에서 들어오는 구현에도 안전하게 dedup
        dedup: dict[str, tuple[str, str, str]] = {}
        for ticker, name, mark in rows:
            if ticker not in dedup:
                dedup[ticker] = (ticker, name, mark)
            else:
                old = dedup[ticker]
                merged_mark = " ".join(x for x in (old[2], mark) if x and x not in old[2])
                dedup[ticker] = (ticker, name or old[1], merged_mark or old[2])
        return list(dedup.values())
    except Exception:  # noqa: BLE001
        return []


def watch_tickers() -> list[str]:
    return [ticker for ticker, _name, _mark in watch_rows()]


def ticker_labels() -> list[str]:
    out: list[str] = []
    for ticker, name, mark in watch_rows():
        label = f"{ticker}  {name}" if name else ticker
        out.append(f"{mark} {label}".strip())
    return out


def order_labels() -> list[str]:
    try:
        from watch_state import cancelable_orders

        return [label for _order_id, label in cancelable_orders()]
    except Exception:  # noqa: BLE001
        return []


def order_id_of(label: str) -> str:
    try:
        from watch_state import order_id_of as pick

        return pick(label)
    except Exception:  # noqa: BLE001
        return (label or "").strip()


def name_of(ticker: str) -> str:
    ticker = ticker_of(ticker)
    for code, name, _mark in watch_rows():
        if code == ticker:
            return name
    return ""


def default_weight() -> str:
    """정책의 후보 비중을 읽되 kstock은 import하지 않는다."""
    import yaml

    path = ROOT / "config" / "policy" / "portfolio_policy.yaml"
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return ""
    node = doc.get("default_candidate_weight")
    if isinstance(node, dict):
        node = node.get("value")
    if node is not None:
        return str(node)
    limit = doc.get("max_position_weight")
    if isinstance(limit, dict):
        limit = limit.get("value")
    try:
        return str(round(float(limit) / 2, 3))
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def run_gui() -> int:  # pragma: no cover - 화면 코드
    import tkinter as tk
    from tkinter import ttk

    problems = check()
    if problems:
        print("명령 표에 문제가 있다. 콘솔을 열지 않는다.")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    root = tk.Tk()
    root.title(TITLE)
    root.geometry("1440x900")
    root.minsize(1180, 720)

    state0 = read_safety()
    is_live = bool(state0.is_live)
    bg = COLORS["live_bg"] if is_live else COLORS["paper_bg"]
    accent = COLORS["live_accent"] if is_live else COLORS["paper_accent"]
    root.configure(bg=bg)

    # ttk 기본 스타일을 조금만 정리한다. 플랫폼 기본 느낌은 유지한다.
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("K.TFrame", background=bg)
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("Card.TLabelframe", background=COLORS["panel"], borderwidth=1)
    style.configure("Card.TLabelframe.Label", background=COLORS["panel"], foreground=COLORS["text"], font=("Malgun Gothic", 10, "bold"))
    style.configure("K.TLabel", background=bg, foreground=COLORS["text"], font=("Malgun Gothic", 9))
    style.configure("Muted.TLabel", background=bg, foreground=COLORS["muted"], font=("Malgun Gothic", 9))
    style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Malgun Gothic", 9))
    style.configure("PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Malgun Gothic", 9))
    style.configure("Title.TLabel", background=bg, foreground=COLORS["text"], font=("Malgun Gothic", 14, "bold"))
    style.configure("Env.TLabel", background=bg, foreground=accent, font=("Malgun Gothic", 18, "bold"))
    style.configure("Treeview", rowheight=28, font=("Malgun Gothic", 9))
    style.configure("Treeview.Heading", font=("Malgun Gothic", 9, "bold"))
    style.configure("TNotebook.Tab", padding=(14, 7), font=("Malgun Gothic", 9, "bold"))

    msgq: queue.Queue = queue.Queue()
    busy = {"on": False}
    interest_busy = {"on": False}
    buttons: list[tuple[tk.Widget, Command]] = []
    fvars: dict[str, tk.StringVar] = {}
    last = {"reconcile": None, "broker": None}
    active_confirmation: dict[str, Command | None] = {"cmd": None}

    # 모든 입력 상태를 먼저 만든다. UI에 보이지 않는 actor도 명령 계약에는 존재한다.
    for key, _label, default, _width in FIELDS:
        if key == "weight" and not default:
            default = default_weight()
        fvars[key] = tk.StringVar(value=default)

    all_cmds = all_commands()
    by_label = {cmd.label: cmd for cmd in all_cmds}

    # ------------------------------------------------------------------
    # Header: 환경 + 안전 상태 + 비상 정지
    # ------------------------------------------------------------------
    header = tk.Frame(root, bg=bg, height=88)
    header.pack(fill="x", padx=14, pady=(12, 6))
    header.pack_propagate(False)

    left_head = tk.Frame(header, bg=bg)
    left_head.pack(side="left", fill="y")
    tk.Label(left_head, text=state0.environment, bg=bg, fg=accent,
             font=("Malgun Gothic", 18, "bold")).pack(side="left", padx=(4, 12))
    title_box = tk.Frame(left_head, bg=bg)
    title_box.pack(side="left", fill="y")
    tk.Label(title_box, text="K-Stock AI Agent", bg=bg, fg=COLORS["text"],
             font=("Malgun Gothic", 14, "bold")).pack(anchor="w")
    tk.Label(title_box, text="개인투자자 운영 콘솔 · 고정계좌", bg=bg, fg=COLORS["muted"],
             font=("Malgun Gothic", 9)).pack(anchor="w", pady=(2, 0))

    halt_cmd = by_label.get("거래 정지") or by_label.get("킬 스위치 발동")
    emergency = tk.Frame(header, bg=bg)
    emergency.pack(side="right", fill="y", padx=(12, 0))
    emergency_btn = tk.Button(
        emergency,
        text="거래 정지",
        width=12,
        bg=COLORS["red"],
        fg="white",
        activebackground="#A93226",
        activeforeground="white",
        relief="flat",
        font=("Malgun Gothic", 11, "bold"),
        state="normal" if halt_cmd else "disabled",
    )
    emergency_btn.pack(side="right", pady=14)

    safety_box = tk.Frame(header, bg=COLORS["panel"], bd=1, relief="solid")
    safety_box.pack(side="right", fill="both", expand=True, padx=(24, 12))
    status_line1 = tk.Label(safety_box, text="", bg=COLORS["panel"], anchor="w",
                            fg=COLORS["text"], font=("Malgun Gothic", 10, "bold"))
    status_line1.pack(fill="x", padx=12, pady=(10, 1))
    status_line2 = tk.Label(safety_box, text="", bg=COLORS["panel"], anchor="w",
                            fg=COLORS["muted"], font=("Malgun Gothic", 9))
    status_line2.pack(fill="x", padx=12, pady=(1, 8))

    # ------------------------------------------------------------------
    # Main body: 관심종목 | 작업 | 선택/확인
    # ------------------------------------------------------------------
    body = ttk.Panedwindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=14, pady=(0, 6))

    watch_panel = ttk.Frame(body, style="Panel.TFrame", width=300)
    work_panel = ttk.Frame(body, style="K.TFrame")
    side_panel = ttk.Frame(body, style="Panel.TFrame", width=330)
    body.add(watch_panel, weight=0)
    body.add(work_panel, weight=1)
    body.add(side_panel, weight=0)

    # ---------------- 관심종목 패널 ----------------
    watch_header = tk.Frame(watch_panel, bg=COLORS["panel"])
    watch_header.pack(fill="x", padx=10, pady=(10, 4))
    tk.Label(watch_header, text="관심종목", bg=COLORS["panel"], fg=COLORS["text"],
             font=("Malgun Gothic", 12, "bold")).pack(side="left")
    watch_count = tk.Label(watch_header, text="0", bg=COLORS["panel"], fg=COLORS["muted"],
                           font=("Malgun Gothic", 9))
    watch_count.pack(side="left", padx=(8, 0))

    sync_btn = tk.Button(
        watch_header,
        text="KIS 새로고침",
        width=11,
        relief="flat",
        bg=COLORS["blue_soft"],
        fg=COLORS["blue"],
        font=("Malgun Gothic", 9, "bold"),
    )
    sync_btn.pack(side="right")

    interest_status = tk.Label(
        watch_panel,
        text="시작 시 KIS에서 자동 동기화합니다.",
        bg=COLORS["panel"],
        fg=COLORS["muted"],
        anchor="w",
        justify="left",
        font=("Malgun Gothic", 8),
    )
    interest_status.pack(fill="x", padx=10, pady=(0, 7))

    search_var = tk.StringVar()
    search_row = tk.Frame(watch_panel, bg=COLORS["panel"])
    search_row.pack(fill="x", padx=10, pady=(0, 7))
    tk.Label(search_row, text="검색", bg=COLORS["panel"], fg=COLORS["muted"],
             font=("Malgun Gothic", 9)).pack(side="left", padx=(0, 6))
    ttk.Entry(search_row, textvariable=search_var).pack(side="left", fill="x", expand=True)

    tree_frame = tk.Frame(watch_panel, bg=COLORS["panel"])
    tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    watch_tree = ttk.Treeview(tree_frame, columns=("ticker", "name", "mark"), show="headings", selectmode="browse")
    watch_tree.heading("ticker", text="코드")
    watch_tree.heading("name", text="종목명")
    watch_tree.heading("mark", text="구분")
    watch_tree.column("ticker", width=68, anchor="center", stretch=False)
    watch_tree.column("name", width=135, anchor="w")
    watch_tree.column("mark", width=52, anchor="center", stretch=False)
    watch_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=watch_tree.yview)
    watch_tree.configure(yscrollcommand=watch_scroll.set)
    watch_scroll.pack(side="right", fill="y")
    watch_tree.pack(side="left", fill="both", expand=True)
    watch_cache: list[tuple[str, str, str]] = []

    def render_watchlist() -> None:
        nonlocal watch_cache
        watch_cache = watch_rows()
        query = search_var.get().strip().lower()
        for iid in watch_tree.get_children(""):
            watch_tree.delete(iid)
        shown = 0
        for ticker, name, mark in watch_cache:
            hay = f"{ticker} {name} {mark}".lower()
            if query and query not in hay:
                continue
            iid = ticker
            if watch_tree.exists(iid):
                iid = f"{ticker}_{shown}"
            watch_tree.insert("", "end", iid=iid, values=(ticker, name, mark))
            shown += 1
        watch_count.config(text=f"{len(watch_cache)}종목")

    search_var.trace_add("write", lambda *_: render_watchlist())

    # ---------------- 작업 패널 ----------------
    quick = tk.Frame(work_panel, bg=bg)
    quick.pack(fill="x", pady=(0, 6))
    tk.Label(quick, text="자주 보는 것", bg=bg, fg=COLORS["muted"],
             font=("Malgun Gothic", 9)).pack(side="left", padx=(2, 8))

    notebook = ttk.Notebook(work_panel)
    notebook.pack(fill="both", expand=True)

    # scrollable tab helper
    def new_scroll_tab(title: str) -> tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(notebook, bg=bg)
        notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=bg)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return outer, inner

    # ---------------- 오른쪽: 선택 종목 / 확인 / 고급입력 ----------------
    selected_card = tk.Frame(side_panel, bg=COLORS["panel"])
    selected_card.pack(fill="x", padx=12, pady=(12, 8))
    tk.Label(selected_card, text="선택 종목", bg=COLORS["panel"], fg=COLORS["text"],
             font=("Malgun Gothic", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    def labeled_entry(parent, row: int, label: str, key: str, width: int = 16, readonly: bool = False):
        tk.Label(parent, text=label, bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Malgun Gothic", 9)).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=fvars[key], width=width)
        if readonly:
            entry.configure(state="readonly")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    selected_card.columnconfigure(1, weight=1)
    ticker_entry = labeled_entry(selected_card, 1, "종목코드", "ticker", 18)
    corp_entry = labeled_entry(selected_card, 2, "회사명", "corp_name", 18)
    qty_entry = labeled_entry(selected_card, 3, "수량", "quantity", 18)
    price_entry = labeled_entry(selected_card, 4, "지정가", "price", 18)
    weight_entry = labeled_entry(selected_card, 5, "후보 비중", "weight", 18)

    # 확인 문구 — 늘 보이되 필요한 문구 하나만 보여 준다.
    confirm_card = tk.Frame(side_panel, bg=COLORS["panel"], bd=1, relief="solid")
    confirm_card.pack(fill="x", padx=12, pady=8)
    tk.Label(confirm_card, text="확인 문구", bg=COLORS["panel"], fg=COLORS["text"],
             font=("Malgun Gothic", 11, "bold")).pack(anchor="w", padx=10, pady=(9, 2))
    confirm_target = tk.Label(confirm_card, text="위험 작업을 선택하면 필요한 문구가 여기에 표시됩니다.",
                              bg=COLORS["panel"], fg=COLORS["muted"], justify="left", anchor="w",
                              wraplength=290, font=("Malgun Gothic", 8))
    confirm_target.pack(fill="x", padx=10, pady=(0, 6))
    confirm_entry = ttk.Entry(confirm_card, textvariable=fvars["confirm"], font=("Consolas", 11))
    confirm_entry.pack(fill="x", padx=10, pady=(0, 4))
    confirm_state = tk.Label(confirm_card, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                             justify="left", anchor="w", wraplength=290, font=("Malgun Gothic", 8))
    confirm_state.pack(fill="x", padx=10, pady=(0, 9))

    # 고급 입력은 기본 접힘. 자주 쓰지 않는 칸을 화면에서 제거한다.
    advanced_wrap = tk.Frame(side_panel, bg=COLORS["panel"])
    advanced_wrap.pack(fill="both", expand=True, padx=12, pady=(5, 10))
    advanced_toggle = tk.Button(advanced_wrap, text="고급 입력 펼치기 ▾", anchor="w", relief="flat",
                                bg=COLORS["panel"], fg=COLORS["blue"], font=("Malgun Gothic", 9, "bold"))
    advanced_toggle.pack(fill="x")
    advanced = tk.Frame(advanced_wrap, bg=COLORS["panel"])
    advanced.columnconfigure(1, weight=1)
    advanced_visible = {"on": False}

    order_combo = None
    adv_keys = [
        ("주문 id", "order_id"),
        ("Thesis id", "thesis_id"),
        ("제외 사유", "why"),
        ("사유", "reason"),
        ("정지 원인", "trigger"),
        ("닫는 사유", "close_reason"),
        ("저장본", "sample_path"),
        ("찾을 사건", "pattern"),
    ]
    for idx, (label, key) in enumerate(adv_keys):
        tk.Label(advanced, text=label, bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Malgun Gothic", 8)).grid(row=idx, column=0, sticky="e", padx=(0, 7), pady=3)
        if key == "order_id":
            order_combo = ttk.Combobox(advanced, textvariable=fvars[key], values=order_labels())
            order_combo.grid(row=idx, column=1, sticky="ew", pady=3)
        else:
            ttk.Entry(advanced, textvariable=fvars[key]).grid(row=idx, column=1, sticky="ew", pady=3)

    def toggle_advanced() -> None:
        advanced_visible["on"] = not advanced_visible["on"]
        if advanced_visible["on"]:
            advanced.pack(fill="x", pady=(6, 0))
            advanced_toggle.config(text="고급 입력 접기 ▴")
        else:
            advanced.pack_forget()
            advanced_toggle.config(text="고급 입력 펼치기 ▾")

    advanced_toggle.config(command=toggle_advanced)

    # ------------------------------------------------------------------
    # 로그: 화면 하단 고정, 지나치게 크지 않게
    # ------------------------------------------------------------------
    logframe = tk.Frame(root, bg=COLORS["panel"], bd=1, relief="solid", height=210)
    logframe.pack(fill="x", padx=14, pady=(0, 12))
    logframe.pack_propagate(False)
    log_head = tk.Frame(logframe, bg=COLORS["panel"])
    log_head.pack(fill="x", padx=8, pady=(7, 3))
    tk.Label(log_head, text="실행 로그", bg=COLORS["panel"], fg=COLORS["text"],
             font=("Malgun Gothic", 10, "bold")).pack(side="left")
    logbox = tk.Text(logframe, height=8, wrap="none", font=("Consolas", 9), bd=0,
                     bg="#FCFCFD", fg=COLORS["text"])
    log_scroll = ttk.Scrollbar(logframe, orient="vertical", command=logbox.yview)
    logbox.configure(yscrollcommand=log_scroll.set)
    log_scroll.pack(side="right", fill="y", padx=(0, 5), pady=(0, 5))
    logbox.pack(fill="both", expand=True, padx=8, pady=(0, 5))
    logbox.tag_configure("ok", foreground=COLORS["text"])
    logbox.tag_configure("warn", foreground=COLORS["warn"])
    logbox.tag_configure("red", foreground=COLORS["red"])
    logbox.tag_configure("cmd", foreground=COLORS["blue"])

    trace = tk.Frame(log_head, bg=COLORS["panel"])
    trace.pack(side="right")
    tk.Label(trace, text="흐름", bg=COLORS["panel"], fg=COLORS["muted"],
             font=("Malgun Gothic", 8)).pack(side="left")
    ttk.Entry(trace, textvariable=fvars["correlation_id"], width=22).pack(side="left", padx=4)

    def log(text: str, tag: str = "ok") -> None:
        logbox.insert("end", text, tag)
        logbox.see("end")

    # ------------------------------------------------------------------
    # 확인 문구 UX
    # ------------------------------------------------------------------
    def current_values() -> dict[str, str]:
        return {key: var.get() for key, var in fvars.items()}

    def render_confirmation() -> None:
        cmd = active_confirmation["cmd"]
        if cmd is None:
            confirm_target.config(text="위험 작업을 선택하면 필요한 문구가 여기에 표시됩니다.", fg=COLORS["muted"])
            typed = fvars["confirm"].get().strip()
            confirm_state.config(text="" if not typed else "현재 선택된 위험 작업이 없습니다.", fg=COLORS["muted"])
            return
        values = current_values()
        hint = confirm_hint(cmd.label, values)
        if hint is None:
            confirm_target.config(text=f"{cmd.label}: 별도 확인 문구가 없습니다.", fg=COLORS["muted"])
            confirm_state.config(text="")
            return
        _what, phrase = hint
        incomplete = "(" in phrase
        confirm_target.config(
            text=f"{cmd.label}\n필요 문구:  {phrase}" + ("\n먼저 종목·수량·가격 등 빈 항목을 채우십시오." if incomplete else ""),
            fg=COLORS["warn"] if incomplete else COLORS["text"],
        )
        typed = fvars["confirm"].get().strip()
        if not typed:
            confirm_state.config(text="문구를 직접 입력한 뒤 같은 작업 버튼을 다시 누르십시오.", fg=COLORS["muted"])
        elif typed == phrase:
            confirm_state.config(text="✓ 확인 문구가 일치합니다.", fg=COLORS["ok"])
        else:
            confirm_state.config(text=mismatch_note(typed, values), fg=COLORS["warn"])

    for key in ("ticker", "quantity", "price", "order_id", "confirm"):
        fvars[key].trace_add("write", lambda *_: render_confirmation())

    # ticker 직접 입력 시 회사명 보정
    def sync_name_from_ticker(*_args) -> None:
        code = ticker_of(fvars["ticker"].get())
        if not code:
            return
        name = name_of(code)
        if name:
            fvars["corp_name"].set(name)

    fvars["ticker"].trace_add("write", sync_name_from_ticker)

    # ------------------------------------------------------------------
    # 실행 / busy 처리
    # ------------------------------------------------------------------
    def set_busy(on: bool) -> None:
        busy["on"] = on
        for widget, cmd in buttons:
            if cmd.never_lock:
                continue
            try:
                widget.config(state="disabled" if on else "normal")
            except tk.TclError:
                pass

    def run(cmd: Command) -> None:
        if busy["on"] and not cmd.never_lock:
            log("[대기] 다른 작업이 실행 중입니다.\n", "warn")
            return

        values = current_values()
        hint = confirm_hint(cmd.label, values)
        if hint is not None:
            active_confirmation["cmd"] = cmd
            render_confirmation()
            phrase = hint[1]
            if "(" in phrase:
                log(missing_hint(cmd, values) + "\n", "warn")
                return
            if values.get("confirm", "") != phrase:
                confirm_entry.focus_set()
                log(missing_hint(cmd, values) + "\n", "warn")
                return

        try:
            args = resolve_inputs(cmd, values)
        except ValueError:
            log(missing_hint(cmd, values) + "\n", "warn")
            return

        if cmd.interactive:
            log(f"[확인] {cmd.label} — 입력한 확인 문구로 실행합니다.\n", "warn")

        set_busy(True)
        # 확인 문구는 1회 사용 후 화면에서 제거한다. args에는 이미 복사됐다.
        if hint is not None:
            fvars["confirm"].set("")
        spawn(
            args,
            ROOT,
            on_line=lambda text: msgq.put(("line", text)),
            on_done=lambda rc: msgq.put(("done", rc)),
        )

    if halt_cmd is not None:
        emergency_btn.config(command=lambda: run(halt_cmd))
        buttons.append((emergency_btn, halt_cmd))

    # ------------------------------------------------------------------
    # KIS 관심종목 자동 동기화
    # ------------------------------------------------------------------
    def start_interest_sync(manual: bool = False) -> None:
        if interest_busy["on"]:
            return
        if not interest_tool_available():
            interest_status.config(text="tools/interest.py가 없습니다. 로컬 관심목록만 표시합니다.", fg=COLORS["warn"])
            render_watchlist()
            return

        interest_busy["on"] = True
        sync_btn.config(state="disabled", text="동기화 중…")
        interest_status.config(text="KIS 관심종목을 가져오는 중입니다…", fg=COLORS["blue"])
        args = interest_sync_args(state0.environment)

        def worker() -> None:
            try:
                completed = subprocess.run(
                    [sys.executable, *args],
                    cwd=str(ROOT),
                    env=child_env(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=45,
                    check=False,
                )
                msgq.put(("interest_done", (completed.returncode, completed.stdout, manual)))
            except Exception as exc:  # noqa: BLE001
                msgq.put(("interest_done", (1, f"{exc}", manual)))

        threading.Thread(target=worker, daemon=True).start()

    sync_btn.config(command=lambda: start_interest_sync(manual=True))

    # ------------------------------------------------------------------
    # 관심종목 선택
    # ------------------------------------------------------------------
    def on_watch_select(_event=None) -> None:
        selected = watch_tree.selection()
        if not selected:
            return
        values = watch_tree.item(selected[0], "values")
        if not values:
            return
        ticker = str(values[0]).strip()
        name = str(values[1]).strip() if len(values) > 1 else ""
        fvars["ticker"].set(ticker)
        if name:
            fvars["corp_name"].set(name)
        qty_entry.focus_set()

    watch_tree.bind("<<TreeviewSelect>>", on_watch_select)
    watch_tree.bind("<Double-Button-1>", on_watch_select)

    # ------------------------------------------------------------------
    # 버튼 생성
    # ------------------------------------------------------------------
    def action_button(parent, cmd: Command, width: int = 15):
        if cmd.danger:
            btn = tk.Button(parent, text=cmd.label, width=width, bg="#FFF1F0", fg=COLORS["red"],
                            activebackground="#FDE2E0", relief="solid", bd=1,
                            font=("Malgun Gothic", 9, "bold"), command=lambda c=cmd: run(c))
        else:
            btn = tk.Button(parent, text=cmd.label, width=width, bg="white", fg=COLORS["text"],
                            activebackground=COLORS["selected"], relief="solid", bd=1,
                            font=("Malgun Gothic", 9), command=lambda c=cmd: run(c))
        buttons.append((btn, cmd))
        return btn

    for label in QUICK_LABELS:
        cmd = by_label.get(label)
        if cmd is None:
            continue
        action_button(quick, cmd, width=11).pack(side="left", padx=3, pady=2)

    # 흐름을 탭으로 바꾼다. 현재 UI의 긴 세로 스크롤을 없애는 핵심 변경.
    for flow in FLOWS:
        _outer, inner = new_scroll_tab(flow.title)
        if flow.note:
            tk.Label(inner, text=flow.note, bg=bg, fg=COLORS["warn"],
                     font=("Malgun Gothic", 9), anchor="w", justify="left").pack(fill="x", padx=14, pady=(12, 5))
        for index, step in enumerate(flow.steps, start=1):
            cmd = step.command()
            card = tk.Frame(inner, bg=COLORS["panel"], bd=1, relief="solid")
            card.pack(fill="x", padx=12, pady=5)
            num = "·" if step.optional else str(index)
            tk.Label(card, text=num, width=3, bg=COLORS["panel"], fg=COLORS["muted"],
                     font=("Malgun Gothic", 10, "bold")).pack(side="left", padx=(8, 2), pady=10)
            action_button(card, cmd, width=14).pack(side="left", padx=(2, 12), pady=8)
            note = ("선택: " if step.optional else "") + step.why
            tk.Label(card, text=note, bg=COLORS["panel"], fg=COLORS["muted"],
                     anchor="w", justify="left", wraplength=650,
                     font=("Malgun Gothic", 9)).pack(side="left", fill="x", expand=True, pady=8)

    # 전체 명령 탭
    _outer, all_inner = new_scroll_tab("전체 명령")
    for section in SECTIONS:
        group = tk.LabelFrame(all_inner, text=section.title, bg=bg, fg=COLORS["text"],
                              font=("Malgun Gothic", 9, "bold"), padx=8, pady=8)
        group.pack(fill="x", padx=12, pady=6)
        grid = tk.Frame(group, bg=bg)
        grid.pack(fill="x")
        for idx, cmd in enumerate(section.commands):
            btn = action_button(grid, cmd, width=14)
            btn.grid(row=idx // 4, column=idx % 4, padx=4, pady=4, sticky="w")
        if section.note:
            tk.Label(group, text=section.note, bg=bg, fg=COLORS["muted"],
                     font=("Malgun Gothic", 8), anchor="w").pack(fill="x", pady=(5, 0))

    if NOT_YET:
        later = tk.LabelFrame(all_inner, text="아직 없는 것", bg=bg, fg=COLORS["muted"],
                              font=("Malgun Gothic", 9, "bold"), padx=8, pady=8)
        later.pack(fill="x", padx=12, pady=8)
        for title, note in NOT_YET:
            tk.Label(later, text=f"{title} — {note}", bg=bg, fg=COLORS["muted"],
                     font=("Malgun Gothic", 8), anchor="w").pack(fill="x")

    # trace 버튼 및 로그 지우기
    trace_cmd = None
    for cmd in all_cmds:
        if cmd.label == "흐름 추적":
            trace_cmd = cmd
            break
    if trace_cmd is not None:
        tk.Button(trace, text="추적", relief="flat", bg=COLORS["blue_soft"], fg=COLORS["blue"],
                  command=lambda c=trace_cmd: run(c)).pack(side="left")
    tk.Button(trace, text="로그 지우기", relief="flat", bg=COLORS["panel"], fg=COLORS["muted"],
              command=lambda: logbox.delete("1.0", "end")).pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------------
    # 상태/메시지 루프
    # ------------------------------------------------------------------
    def refresh_safety() -> None:
        st = read_safety()
        st.last_reconcile = last["reconcile"]
        st.last_broker = last["broker"]
        status_line1.config(text=format_line(st), fg=COLORS["red"] if st.is_red else COLORS["ok"])
        second = format_second_line(st)
        if st.kill_reason:
            second += f"   |   {st.kill_reason}"
        status_line2.config(text=second)
        root.after(2000, refresh_safety)

    def drain() -> None:
        try:
            while True:
                kind, payload = msgq.get_nowait()
                if kind == "line":
                    text = str(payload)
                    tag = "cmd" if text.startswith("$ ") else "ok"
                    if "차단" in text or "[중단]" in text:
                        tag = "red"
                    elif "참고" in text or text.lstrip().startswith("!") or "경고" in text:
                        tag = "warn"
                    log(text, tag)
                elif kind == "done":
                    set_busy(False)
                    render_watchlist()
                    if order_combo is not None:
                        order_combo["values"] = order_labels()
                elif kind == "interest_done":
                    rc, output, manual = payload
                    interest_busy["on"] = False
                    sync_btn.config(state="normal", text="KIS 새로고침")
                    render_watchlist()
                    now_text = datetime.now().strftime("%H:%M:%S")
                    if rc == 0:
                        interest_status.config(text=f"KIS 동기화 완료 · {now_text}", fg=COLORS["ok"])
                        if manual:
                            log(f"[관심종목] KIS 동기화 완료 — {len(watch_rows())}종목\n", "ok")
                    else:
                        interest_status.config(text="KIS 동기화 실패 · 로컬 목록 표시 중", fg=COLORS["warn"])
                        tail = "\n".join(str(output).strip().splitlines()[-4:])
                        log("[관심종목] 자동 동기화에 실패했습니다. .env와 KIS_HTS_USER_ID를 확인하십시오.\n", "warn")
                        if tail:
                            log(tail + "\n", "warn")
        except queue.Empty:
            pass
        root.after(80, drain)

    def pick_id(event) -> None:
        index = logbox.index(f"@{event.x},{event.y}")
        word = logbox.get(f"{index} wordstart", f"{index} wordend").strip()
        if word.startswith(("evt_", "q_", "ord_", "int_", "appr_", "corr_")):
            fvars["correlation_id"].set(word)
            log(f"[선택] {word}\n", "warn")

    logbox.bind("<Double-Button-1>", pick_id)

    # 초기 렌더링: 캐시를 즉시 보여 준 뒤 KIS를 자동 동기화한다.
    render_watchlist()
    render_confirmation()
    refresh_safety()
    drain()
    log("K-Stock 운영 콘솔을 시작했습니다.\n")
    log("관심종목은 시작 시 KIS에서 자동 동기화하며, 실패하면 마지막 로컬 목록을 사용합니다.\n", "warn")
    log("확인 문구는 GUI가 채우지 않습니다. 필요한 위험 작업을 선택한 뒤 직접 입력하십시오.\n\n", "warn")

    # 창을 먼저 보여 준 뒤 네트워크 조회를 시작한다. UI 기동이 KIS 응답에 막히지 않는다.
    root.after(350, lambda: start_interest_sync(manual=False))

    root.mainloop()
    return 0


# ---------------------------------------------------------------------------
def main() -> int:
    if "--flows" in sys.argv:
        for flow in FLOWS:
            print(f"\n[{flow.title}]")
            if flow.note:
                print(f"  {flow.note}")
            for index, step in enumerate(flow.steps, start=1):
                cmd = step.command()
                mark = f"{index}." if not step.optional else " ·"
                args = " ".join(cmd.args)
                print(f"  {mark} {cmd.label:<14}tools/{cmd.script} {args}")
                print(f"      {step.why}")
        return 0
    if "--print" in sys.argv:
        import console_commands
        return console_commands.main()
    if "--check" in sys.argv:
        problems = check()
        for problem in problems:
            print(f"  - {problem}")
        return 1 if problems else 0
    try:
        return run_gui()
    except ImportError as exc:
        print(f"[중단] Tk를 쓸 수 없습니다: {exc}")
        print("       명령 표만 보려면: python tools/console.py --print")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
