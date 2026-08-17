from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .models import CommandContext, LockGroup, RiskClass

ArgBuilder = Callable[[CommandContext], list[str]]


@dataclass(frozen=True)
class CommandSpec:
    key: str
    label: str
    cli_path: tuple[str, ...]
    risk_class: RiskClass
    lock_group: LockGroup
    build_args: ArgBuilder
    implemented: bool = True
    human_confirmation: bool = False
    confirmation_phrase: str | None = None
    always_available: bool = False

    def argv(self, ctx: CommandContext, runner: Sequence[str]) -> list[str]:
        if not self.implemented:
            raise ValueError(f"Command is not implemented: {self.key}")
        return [
            *runner,
            *self.cli_path,
            *self.build_args(ctx),
            "--environment", ctx.environment,
            "--correlation-id", ctx.correlation_id,
            "--output", "jsonl",
        ]


def _none(_ctx: CommandContext) -> list[str]:
    return []


def _confirmation(ctx: CommandContext) -> list[str]:
    return ["--confirmation", str(ctx.values.get("confirmation", ""))]


def _reason(ctx: CommandContext) -> list[str]:
    return ["--reason", str(ctx.values.get("reason", ""))]


def _resume(ctx: CommandContext) -> list[str]:
    return [
        "--confirmation", str(ctx.values.get("confirmation", "")),
        "--reason", str(ctx.values.get("reason", "")),
    ]


def _quote(ctx: CommandContext) -> list[str]:
    return ["--symbol", str(ctx.values.get("symbol", ""))]


def _buying_power(ctx: CommandContext) -> list[str]:
    return [
        "--symbol", str(ctx.values.get("symbol", "")),
        "--price", str(ctx.values.get("price", 0)),
    ]


def _interest_group(ctx: CommandContext) -> list[str]:
    return ["--group-code", str(ctx.values.get("group_code", ""))]


def _mode(ctx: CommandContext) -> list[str]:
    return ["--mode", str(ctx.values.get("mode", ""))]


def _enabled(ctx: CommandContext) -> list[str]:
    return ["--enabled", "true" if ctx.values.get("enabled", True) else "false"]


def _recent(ctx: CommandContext) -> list[str]:
    return ["--limit", str(ctx.values.get("limit", 50))]


def _trace(ctx: CommandContext) -> list[str]:
    return [
        "--target-correlation-id",
        str(ctx.values.get("target_correlation_id", "")),
    ]


COMMANDS: dict[str, CommandSpec] = {
    "quick_check": CommandSpec("quick_check", "빠른 점검", ("startup", "quick-check"), RiskClass.R0, LockGroup.STARTUP, _none),
    "full_check": CommandSpec("full_check", "전체 점검", ("startup", "full-check"), RiskClass.R0, LockGroup.STARTUP, _none),
    "gate_status": CommandSpec("gate_status", "게이트 상태", ("gate", "status"), RiskClass.R0, LockGroup.STARTUP, _none),
    "gate_open": CommandSpec("gate_open", "게이트 열기", ("gate", "open"), RiskClass.R2, LockGroup.STARTUP, _confirmation, human_confirmation=True, confirmation_phrase="START TRADING"),
    "gate_close": CommandSpec("gate_close", "게이트 닫기", ("gate", "close"), RiskClass.R0, LockGroup.STARTUP, _reason),

    "account_query": CommandSpec("account_query", "계좌 조회", ("account", "query"), RiskClass.R0, LockGroup.QUERY, _none),
    "quote_query": CommandSpec("quote_query", "시세 조회", ("quote", "query"), RiskClass.R0, LockGroup.QUERY, _quote),
    "buying_power": CommandSpec("buying_power", "매수가능금액", ("account", "buying-power"), RiskClass.R0, LockGroup.QUERY, _buying_power),
    "dart_collect": CommandSpec("dart_collect", "OpenDART 수집", ("dart", "collect"), RiskClass.R0, LockGroup.QUERY, _none),
    "dart_replay": CommandSpec("dart_replay", "저장본 재현", ("dart", "replay"), RiskClass.R0, LockGroup.QUERY, _none),
    "interest_groups": CommandSpec("interest_groups", "관심그룹 조회", ("interest", "groups"), RiskClass.R0, LockGroup.QUERY, _none),
    "interest_sync": CommandSpec("interest_sync", "관심종목 동기화", ("interest", "sync"), RiskClass.R0, LockGroup.QUERY, _interest_group),
    "interest_show": CommandSpec("interest_show", "Watch 대상 보기", ("interest", "show"), RiskClass.R0, LockGroup.QUERY, _none),
    "quote_live": CommandSpec("quote_live", "시세 LIVE", ("demo", "quote-mode"), RiskClass.R0, LockGroup.DEMO, _mode),
    "quote_suspended": CommandSpec("quote_suspended", "거래정지 시세", ("demo", "quote-mode"), RiskClass.R0, LockGroup.DEMO, _mode),

    "reconcile": CommandSpec("reconcile", "대사 실행", ("reconcile", "run"), RiskClass.R0, LockGroup.RECONCILE, _none),
    "recon_match": CommandSpec("recon_match", "대사 MATCH 주입", ("demo", "reconciliation-mode"), RiskClass.R0, LockGroup.DEMO, _mode),
    "recon_mismatch": CommandSpec("recon_mismatch", "대사 MISMATCH 주입", ("demo", "reconciliation-mode"), RiskClass.R1, LockGroup.DEMO, _mode),
    "recon_unknown": CommandSpec("recon_unknown", "대사 UNKNOWN 주입", ("demo", "reconciliation-mode"), RiskClass.R1, LockGroup.DEMO, _mode),
    "repair_demo": CommandSpec("repair_demo", "데모 복구", ("reconcile", "repair-demo"), RiskClass.R1, LockGroup.RECONCILE, _confirmation, human_confirmation=True, confirmation_phrase="CONFIRM"),

    "seed_open_order": CommandSpec("seed_open_order", "미체결 주문 주입", ("demo", "seed-open-order"), RiskClass.R0, LockGroup.DEMO, _none),
    "seed_unknown_order": CommandSpec("seed_unknown_order", "UNKNOWN 주문 주입", ("demo", "seed-unknown-order"), RiskClass.R1, LockGroup.DEMO, _none),
    "cancel_open_orders": CommandSpec("cancel_open_orders", "미체결 주문 취소", ("orders", "cancel-open"), RiskClass.R0, LockGroup.EMERGENCY, _confirmation, human_confirmation=True, confirmation_phrase="CONFIRM", always_available=True),

    "kill_status": CommandSpec("kill_status", "킬 스위치 상태", ("kill", "status"), RiskClass.R0, LockGroup.KILL_SWITCH, _none),
    "resume": CommandSpec("resume", "사람 확인 후 재가동", ("ops", "resume"), RiskClass.R2, LockGroup.KILL_SWITCH, _resume, human_confirmation=True, confirmation_phrase="RESUME TRADING"),

    "audit_health": CommandSpec("audit_health", "감사 건강도", ("audit", "health"), RiskClass.R0, LockGroup.AUDIT, _none),
    "audit_recent": CommandSpec("audit_recent", "최근 감사 기록", ("audit", "recent"), RiskClass.R0, LockGroup.AUDIT, _recent),
    "audit_trace": CommandSpec("audit_trace", "correlation 추적", ("audit", "trace"), RiskClass.R0, LockGroup.AUDIT, _trace),
    "audit_fail_on": CommandSpec("audit_fail_on", "감사 실패 주입", ("demo", "audit-failure"), RiskClass.R1, LockGroup.DEMO, _enabled),
    "audit_fail_off": CommandSpec("audit_fail_off", "감사 실패 해제", ("demo", "audit-failure"), RiskClass.R0, LockGroup.DEMO, _enabled),

    "halt": CommandSpec("halt", "거래 정지", ("ops", "halt"), RiskClass.R0, LockGroup.EMERGENCY, _reason, always_available=True),
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cli_launcher() -> Path:
    return project_root() / "run_cli.py"


def default_runner() -> list[str]:
    """현재 프로젝트의 CLI 진입점을 정확히 실행한다.

    `python run_cli.py`는 작업 디렉터리에 동명 패키지가 있으면
    다른 CLI를 선택할 수 있으므로 사용하지 않는다.
    """
    return [sys.executable, str(cli_launcher())]


def source_root() -> Path:
    return Path(__file__).resolve().parents[1]
