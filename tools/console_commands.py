"""CLI contracts for the authority-free console. Never import kstock here."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Sequence

class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"

class RiskClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    CONTROL = "CONTROL"
    ECONOMIC = "ECONOMIC"

class LockGroup(str, Enum):
    GENERAL = "GENERAL"
    EXTERNAL_QUERY = "EXTERNAL_QUERY"
    CONTROL = "CONTROL"

class ResultStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"

EXIT_CODE_STATUS = {
    0: ResultStatus.SUCCESS,
    10: ResultStatus.BLOCKED,
    20: ResultStatus.ERROR,
    30: ResultStatus.ERROR,
    40: ResultStatus.ERROR,
    50: ResultStatus.UNKNOWN,
    130: ResultStatus.CANCELLED,
}

@dataclass(frozen=True, slots=True)
class CommandContext:
    environment: Environment
    correlation_id: str
    reason: str = ""

ArgBuilder = Callable[[CommandContext], list[str]]

@dataclass(frozen=True, slots=True)
class CommandSpec:
    key: str
    label: str
    cli_path: tuple[str, ...]
    risk_class: RiskClass
    lock_group: LockGroup
    build_args: ArgBuilder
    implemented: bool = True
    human_confirmation: bool = False
    always_available: bool = False

    def argv(self, ctx: CommandContext, runner: Sequence[str]) -> list[str]:
        if not self.implemented:
            raise ValueError(f"Command is not implemented: {self.key}")
        return [
            *runner, *self.cli_path, *self.build_args(ctx),
            "--environment", ctx.environment.value,
            "--correlation-id", ctx.correlation_id,
            "--output", "jsonl",
        ]

@dataclass(slots=True)
class ConfirmationState:
    required_phrase: str
    entered_phrase: str = ""

    @property
    def can_submit(self) -> bool:
        return confirmation_matches(self.required_phrase, self.entered_phrase)

def confirmation_matches(required: str, entered: str) -> bool:
    return entered == required

def status_from_exit_code(code: int) -> ResultStatus:
    return EXIT_CODE_STATUS.get(code, ResultStatus.ERROR)

def _none(_: CommandContext) -> list[str]:
    return []

def _reason(ctx: CommandContext) -> list[str]:
    if not ctx.reason.strip():
        raise ValueError("reason is required")
    return ["--reason", ctx.reason]

def build_registry() -> dict[str, CommandSpec]:
    specs = [
        CommandSpec("quick_check", "빠른 점검", ("preflight", "quick"), RiskClass.READ_ONLY, LockGroup.GENERAL, _none),
        CommandSpec("full_check", "전체 점검", ("preflight", "full"), RiskClass.READ_ONLY, LockGroup.GENERAL, _none),
        CommandSpec("account_summary", "계좌 조회", ("account", "summary"), RiskClass.READ_ONLY, LockGroup.EXTERNAL_QUERY, _none),
        CommandSpec("disclosure_collect", "공시 수집", ("disclosure", "collect"), RiskClass.READ_ONLY, LockGroup.EXTERNAL_QUERY, _none),
        CommandSpec("reconcile_run", "대사 실행", ("reconcile", "run"), RiskClass.READ_ONLY, LockGroup.GENERAL, _none),
        CommandSpec("gate_status", "게이트 상태", ("gate", "status"), RiskClass.READ_ONLY, LockGroup.GENERAL, _none),
        CommandSpec("audit_recent", "감사 조회", ("audit", "recent"), RiskClass.READ_ONLY, LockGroup.GENERAL, _none),
        CommandSpec("gate_close", "거래 정지", ("gate", "close"), RiskClass.CONTROL, LockGroup.CONTROL, _reason, always_available=True),
        CommandSpec("kill_switch_trigger", "킬 스위치 발동", ("kill-switch", "trigger"), RiskClass.CONTROL, LockGroup.CONTROL, _reason, always_available=True),
    ]
    return {spec.key: spec for spec in specs}

def visible_specs(registry: Mapping[str, CommandSpec]) -> list[CommandSpec]:
    return [spec for spec in registry.values() if spec.implemented]

def command_manifest(registry: Mapping[str, CommandSpec]) -> list[dict[str, object]]:
    return [{
        "key": s.key,
        "label": s.label,
        "cli_path": list(s.cli_path),
        "risk_class": s.risk_class.value,
        "lock_group": s.lock_group.value,
        "human_confirmation": s.human_confirmation,
        "always_available": s.always_available,
    } for s in visible_specs(registry)]
