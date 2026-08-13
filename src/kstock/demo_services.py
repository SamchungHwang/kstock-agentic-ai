from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .audit_store import (
    append_audit,
    health,
    probe_writable,
    read_recent,
    set_failure_injection,
    trace,
)
from .env_config import resolve_kis_credentials
from .fixed_identity import OWNER_ACTOR_ID, fixed_account_ref
from .external_adapter import probe_full_check_boundaries, record_external_call
from .models import ResultStatus
from .state_store import (
    configure_runtime_environment,
    require_runtime_environment,
    data_dir,
    now_iso,
    read_state,
    update_state,
)


class ServiceResult:
    def __init__(
        self,
        status: ResultStatus,
        code: str,
        message: str,
        payload: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.payload = payload or {}
        self.next_action = next_action


def _audit(
    corr: str,
    event: str,
    result: ServiceResult,
    actor: str = "cli",
    *,
    required: bool = False,
) -> bool:
    try:
        append_audit(
            event=event,
            status=result.status.value,
            correlation_id=corr,
            actor=actor,
            message=result.message,
            payload={"code": result.code, **result.payload},
        )
        return True
    except OSError:
        if required:
            raise
        return False


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _unknown_orders(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        order for order in state.get("orders", [])
        if order.get("state") == "UNKNOWN"
    ]


def _open_orders(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        order for order in state.get("orders", [])
        if order.get("state") in {"SUBMITTED", "PARTIALLY_FILLED"}
    ]


def _full_check_valid_for_current_state(
    state: dict[str, Any],
    *,
    max_age: timedelta = timedelta(minutes=10),
) -> tuple[bool, str]:
    check = state.get("last_full_check", {})
    if check.get("status") != "PASS":
        return False, "최근 전체 점검이 PASS가 아닙니다."

    checked_at = _parse_iso(check.get("checked_at"))
    reconciliation_at = _parse_iso(
        state.get("last_reconciliation", {}).get("checked_at")
    )
    if checked_at is None:
        return False, "전체 점검 시각이 없습니다."
    if datetime.now().astimezone() - checked_at > max_age:
        return False, "전체 점검 결과가 오래됐습니다."
    if reconciliation_at and checked_at < reconciliation_at:
        return False, "최근 대사 이후 전체 점검을 다시 실행해야 합니다."
    return True, "전체 점검이 최신입니다."


def start_console_session(corr: str, environment: str = "PAPER") -> ServiceResult:
    """프로그램 기동 시 이전 세션의 OPEN 게이트를 신뢰하지 않는다.

    HALTED는 사고 상태이므로 그대로 유지하고, OPEN만 CLOSED로 내린다.
    """
    environment = configure_runtime_environment(environment)
    account_ref = fixed_account_ref(environment).value
    session_id = "session_" + uuid4().hex[:12]

    def mutate(state):
        state["environment"] = environment
        state["account_ref"] = account_ref
        state["owner_actor_id"] = OWNER_ACTOR_ID
        state["session"] = {
            "session_id": session_id,
            "started_at": now_iso(),
        }
        if state["gate"]["state"] == "OPEN":
            state["gate"].update({
                "state": "CLOSED",
                "changed_at": now_iso(),
                "changed_by": "startup",
                "reason": "새 Console 세션 시작: 이전 OPEN 상태 폐기",
            })

    state = update_state(mutate)
    result = ServiceResult(
        ResultStatus.SUCCESS,
        "CONSOLE_SESSION_STARTED",
        "Console 세션을 시작했습니다. 거래 게이트는 자동으로 열리지 않습니다.",
        {"session": state["session"], "gate": state["gate"], "environment": state["environment"], "account_ref": state["account_ref"], "owner_actor_id": OWNER_ACTOR_ID},
    )
    _audit(corr, "CONSOLE_SESSION_STARTED", result, actor="startup")
    return result


def quick_check(corr: str, environment: str = "PAPER") -> ServiceResult:
    """로컬 상태만 점검한다. 외부 경계 어댑터를 호출하지 않는다."""
    environment = require_runtime_environment(environment)
    try:
        state = read_state()
        audit_status, audit_message = health(check_write=True)
        blockers: list[str] = []
        credentials = resolve_kis_credentials(environment)
        credential_errors = credentials.validation_errors()
        if credential_errors:
            blockers.append("KIS_ENV_INVALID")
        if state["gate"]["state"] == "UNKNOWN":
            blockers.append("GATE_UNKNOWN")
        if audit_status not in {"HEALTHY", "DEGRADED"}:
            blockers.append("AUDIT_UNHEALTHY")
        unknown_count = len(_unknown_orders(state))
        if unknown_count:
            blockers.append("UNKNOWN_ORDERS")

        update_state(lambda s: s.update({"audit_health": audit_status}))
        payload = {
            "checks": [
                {"id": "state_store", "status": "PASS", "message": "로컬 상태 읽기 정상"},
                {"id": "gate", "status": "PASS", "message": state["gate"]["state"]},
                {"id": "audit", "status": audit_status, "message": audit_message},
                {
                    "id": "kis_environment",
                    "status": "FAIL" if credential_errors else "PASS",
                    "message": "KIS 환경변수 확인",
                    "details": credentials.safe_summary(),
                },
                {
                    "id": "unknown_orders",
                    "status": "FAIL" if unknown_count else "PASS",
                    "message": f"미해결 UNKNOWN 주문 {unknown_count}건",
                },
            ],
            "blockers": blockers,
            "external_boundary_called": False,
        }
        result = ServiceResult(
            ResultStatus.BLOCKED if blockers else ResultStatus.SUCCESS,
            "QUICK_CHECK_BLOCKED" if blockers else "QUICK_CHECK_OK",
            "빠른 점검에서 차단 항목이 발견됐습니다."
            if blockers else "빠른 점검을 통과했습니다.",
            payload,
        )
    except Exception as exc:
        result = ServiceResult(ResultStatus.UNKNOWN, "QUICK_CHECK_UNKNOWN", str(exc))
    _audit(corr, "STARTUP_QUICK_CHECK", result)
    return result


def full_check(corr: str, environment: str = "PAPER") -> ServiceResult:
    """명시적 실행에서만 외부 경계 어댑터를 호출하는 전체 점검."""
    environment = require_runtime_environment(environment)
    probes = probe_full_check_boundaries(environment)
    state = read_state()
    audit_status, audit_message = health(check_write=True)
    unknown_count = len(_unknown_orders(state))
    reconcile_status = state["last_reconciliation"]["status"]

    blockers: list[str] = []
    env_probe = probes[0]
    if env_probe.get("status") != "PASS":
        blockers.append("KIS_ENV_INVALID")
    if reconcile_status != "MATCH":
        blockers.append("RECONCILIATION_NOT_MATCH")
    if audit_status not in {"HEALTHY", "DEGRADED"}:
        blockers.append("AUDIT_UNHEALTHY")
    if unknown_count:
        blockers.append("UNKNOWN_ORDERS")

    checked_at = now_iso()
    status = "PASS" if not blockers else "BLOCKED"
    message = (
        "전체 점검을 통과했습니다."
        if not blockers
        else "전체 점검은 완료됐지만 거래를 시작하거나 재가동할 수 없습니다."
    )
    full_check_state = {
        "status": status,
        "checked_at": checked_at,
        "message": message,
        "blockers": blockers,
        "reconciliation_checked_at": state["last_reconciliation"].get("checked_at"),
    }

    def mutate(s):
        s["last_full_check"] = full_check_state
        s["audit_health"] = audit_status

    update_state(mutate)
    payload = {
        "checks": [
            {
                "id": "kis_environment",
                "status": env_probe.get("status", "FAIL"),
                "message": "KIS 환경변수 확인",
                "details": env_probe.get("credentials", {}),
            },
            {"id": "external_boundaries", "status": "PASS", "message": "DEMO 외부 경계 어댑터 호출 완료"},
            {"id": "audit", "status": audit_status, "message": audit_message},
            {"id": "reconciliation", "status": reconcile_status, "message": state["last_reconciliation"]["message"]},
            {"id": "unknown_orders", "status": "FAIL" if unknown_count else "PASS", "message": f"UNKNOWN {unknown_count}건"},
            {
                "id": "kill_switch",
                "status": "WARN" if state["kill_switch"]["state"] == "ON" else "PASS",
                "message": state["kill_switch"]["state"],
            },
        ],
        "blockers": blockers,
        "external_probes": probes,
        "demo_mode": True,
    }
    result = ServiceResult(
        ResultStatus.SUCCESS if not blockers else ResultStatus.BLOCKED,
        "FULL_CHECK_OK" if not blockers else "FULL_CHECK_BLOCKED",
        message,
        payload,
        None if not blockers else "차단 원인을 해소하고 전체 점검을 다시 실행하십시오.",
    )
    _audit(corr, "STARTUP_FULL_CHECK", result)
    return result


def gate_status(corr: str) -> ServiceResult:
    state = read_state()
    result = ServiceResult(
        ResultStatus.SUCCESS,
        "GATE_STATUS_OK",
        "거래 게이트 상태를 조회했습니다.",
        {"gate": state["gate"], "session": state["session"]},
    )
    _audit(corr, "GATE_STATUS", result)
    return result


def open_gate(corr: str, confirmation: str) -> ServiceResult:
    state = read_state()
    audit_status, audit_message = health(check_write=True)
    full_ok, full_message = _full_check_valid_for_current_state(state)

    if confirmation != "START TRADING":
        result = ServiceResult(ResultStatus.BLOCKED, "CONFIRMATION_MISMATCH", "확인 문구가 일치하지 않습니다.")
    elif audit_status not in {"HEALTHY", "DEGRADED"}:
        result = ServiceResult(ResultStatus.BLOCKED, "AUDIT_UNHEALTHY", audit_message)
    elif state["last_reconciliation"]["status"] != "MATCH":
        result = ServiceResult(ResultStatus.BLOCKED, "RECONCILIATION_NOT_MATCH", "최근 대사가 MATCH가 아닙니다.")
    elif state["kill_switch"]["state"] == "ON":
        result = ServiceResult(ResultStatus.BLOCKED, "KILL_SWITCH_ON", "킬 스위치가 켜져 있습니다.")
    elif _unknown_orders(state):
        result = ServiceResult(ResultStatus.BLOCKED, "UNKNOWN_ORDERS", "미해결 UNKNOWN 주문이 있습니다.")
    elif not full_ok:
        result = ServiceResult(ResultStatus.BLOCKED, "FULL_CHECK_NOT_CURRENT", full_message)
    else:
        try:
            probe_writable()
            append_audit(
                event="GATE_OPEN_PREPARE",
                status="SUCCESS",
                correlation_id=corr,
                actor=OWNER_ACTOR_ID,
                message="거래 게이트 열기 전제조건을 확인했습니다.",
                payload={"confirmation": "START TRADING"},
            )

            def mutate(s):
                s["gate"].update({
                    "state": "OPEN",
                    "changed_at": now_iso(),
                    "changed_by": OWNER_ACTOR_ID,
                    "reason": "START TRADING 확인",
                })

            state = update_state(mutate)
            result = ServiceResult(ResultStatus.SUCCESS, "GATE_OPENED", "거래 게이트를 열었습니다.", state["gate"])
            try:
                _audit(corr, "GATE_OPEN", result, actor=OWNER_ACTOR_ID, required=True)
            except OSError as exc:
                update_state(lambda s: s["gate"].update({
                    "state": "CLOSED",
                    "changed_at": now_iso(),
                    "changed_by": "audit_guard",
                    "reason": "감사 기록 실패로 게이트 열기 롤백",
                }))
                result = ServiceResult(ResultStatus.ERROR, "AUDIT_COMMIT_FAILED", str(exc))
        except OSError as exc:
            result = ServiceResult(ResultStatus.BLOCKED, "AUDIT_UNHEALTHY", str(exc))

    if result.code not in {"GATE_OPENED", "AUDIT_COMMIT_FAILED"}:
        _audit(corr, "GATE_OPEN", result, actor=OWNER_ACTOR_ID)
    return result


def close_gate(corr: str, reason: str = "사용자 요청") -> ServiceResult:
    def mutate(s):
        s["gate"].update({
            "state": "CLOSED",
            "changed_at": now_iso(),
            "changed_by": OWNER_ACTOR_ID,
            "reason": reason.strip() or "사용자 요청",
        })

    state = update_state(mutate)
    result = ServiceResult(ResultStatus.SUCCESS, "GATE_CLOSED", "거래 게이트를 닫았습니다.", state["gate"])
    persisted = _audit(corr, "GATE_CLOSE", result, actor=OWNER_ACTOR_ID)
    result.payload = {**result.payload, "audit_persisted": persisted}
    return result


def account_query(corr: str, environment: str = "PAPER") -> ServiceResult:
    environment = require_runtime_environment(environment)
    credentials = resolve_kis_credentials(environment)
    if credentials.validation_errors():
        result = ServiceResult(
            ResultStatus.BLOCKED,
            "KIS_ENV_INVALID",
            "KIS 환경변수가 올바르지 않습니다.",
            {"credentials": credentials.safe_summary()},
            "프로젝트 루트의 .env를 확인하고 tools/doctor_env.py를 실행하십시오.",
        )
        _audit(corr, "ACCOUNT_QUERY", result)
        return result
    boundary = record_external_call("kis_account_query")
    state = read_state()
    quote = state.get("quote_snapshot") or {}
    price_state = quote.get("price_state", "LIVE")
    display_price = int(quote.get("display_price", 82_400))
    risk_price = int(quote.get("risk_price", display_price))
    snapshot = {
        "account_ref": credentials.account_ref,
        "broker_account": credentials.safe_summary()["account"],
        "environment": credentials.environment,
        "cash_krw": 9_920_000,
        "buying_power_krw": 9_870_000,
        "positions": [{
            "symbol": "005930",
            "name": "삼성전자",
            "quantity": 1,
            "price_state": price_state,
            "display_value_krw": display_price,
            "risk_value_krw": risk_price,
        }],
        "broker_as_of": now_iso(),
        "fetched_at": now_iso(),
        "external_boundary": boundary,
        "demo_mode": True,
    }
    update_state(lambda s: s.update({"account_snapshot": snapshot}))
    result = ServiceResult(ResultStatus.SUCCESS, "ACCOUNT_QUERY_OK", "계좌 조회를 완료했습니다.", snapshot)
    _audit(corr, "ACCOUNT_QUERY", result)
    return result


def inject_quote_mode(corr: str, mode: str) -> ServiceResult:
    mode = mode.upper()
    if mode not in {"LIVE", "SUSPENDED"}:
        result = ServiceResult(ResultStatus.ERROR, "INVALID_QUOTE_MODE", "LIVE 또는 SUSPENDED만 허용합니다.")
    else:
        update_state(lambda s: s["demo"].update({"quote_mode": mode}))
        result = ServiceResult(ResultStatus.SUCCESS, "QUOTE_MODE_SET", f"시세 모드를 {mode}로 설정했습니다.", {"mode": mode})
    _audit(corr, "DEMO_QUOTE_MODE", result, actor=OWNER_ACTOR_ID)
    return result


def quote_query(corr: str, symbol: str) -> ServiceResult:
    if not symbol.isdigit() or len(symbol) != 6:
        result = ServiceResult(ResultStatus.ERROR, "INVALID_SYMBOL", "종목코드는 숫자 6자리여야 합니다.")
    else:
        boundary = record_external_call("kis_quote_query")
        mode = read_state()["demo"].get("quote_mode", "LIVE")
        display_price = 82_400
        if mode == "SUSPENDED":
            price_state = "STALE"
            risk_price = 57_680  # DEMO: 30% haircut. 실제 비율은 위험 정책이 소유한다.
            message = "거래정지 시세를 조회했습니다. 마지막 체결가는 정상 시가로 사용하지 않습니다."
            code = "QUOTE_STALE"
        else:
            price_state = "LIVE"
            risk_price = display_price
            message = "시세 조회를 완료했습니다."
            code = "QUOTE_QUERY_OK"
        snapshot = {
            "symbol": symbol,
            "name": "삼성전자" if symbol == "005930" else "데모종목",
            "display_price": display_price,
            "risk_price": risk_price,
            "bid1": None if price_state == "STALE" else 82_300,
            "ask1": None if price_state == "STALE" else 82_400,
            "volume": 12_345_678,
            "price_state": price_state,
            "last_trade_at": now_iso(),
            "data_as_of": now_iso(),
            "fetched_at": now_iso(),
            "risk_valuation_reason": "SUSPENDED_HAIRCUT" if price_state == "STALE" else "LIVE_MARK",
            "external_boundary": boundary,
            "demo_mode": True,
        }
        update_state(lambda s: s.update({"quote_snapshot": snapshot}))
        result = ServiceResult(ResultStatus.SUCCESS, code, message, snapshot)
    _audit(corr, "QUOTE_QUERY", result)
    return result


def buying_power_query(corr: str, symbol: str, price: int, environment: str = "PAPER") -> ServiceResult:
    environment = require_runtime_environment(environment)
    credentials = resolve_kis_credentials(environment)
    if credentials.validation_errors():
        result = ServiceResult(
            ResultStatus.BLOCKED,
            "KIS_ENV_INVALID",
            "KIS 환경변수가 올바르지 않습니다.",
            {"credentials": credentials.safe_summary()},
            "프로젝트 루트의 .env를 확인하십시오.",
        )
    elif not symbol.isdigit() or len(symbol) != 6 or price <= 0:
        result = ServiceResult(ResultStatus.ERROR, "INVALID_BUYING_POWER_INPUT", "종목코드와 가격을 확인하십시오.")
    else:
        boundary = record_external_call("kis_buying_power_query")
        snapshot = {
            "symbol": symbol,
            "price": price,
            "account_ref": credentials.account_ref,
            "broker_account": credentials.safe_summary()["account"],
            "environment": credentials.environment,
            "buying_power_krw": 9_870_000,
            "max_quantity": 9_870_000 // price,
            "fetched_at": now_iso(),
            "external_boundary": boundary,
            "demo_mode": True,
        }
        update_state(lambda s: s.update({"buying_power_snapshot": snapshot}))
        result = ServiceResult(ResultStatus.SUCCESS, "BUYING_POWER_OK", "매수가능금액을 조회했습니다.", snapshot)
    _audit(corr, "BUYING_POWER_QUERY", result)
    return result


def dart_collect(corr: str) -> ServiceResult:
    boundary = record_external_call("opendart_collect")
    batch_dir = data_dir() / "raw" / "opendart" / corr
    batch_dir.mkdir(parents=True, exist_ok=True)
    response = {
        "status": "000",
        "message": "정상",
        "list": [
            {"corp_name": "데모전자", "report_nm": "분기보고서", "rcept_no": "20260805000001"},
            {"corp_name": "데모반도체", "report_nm": "주요사항보고서", "rcept_no": "20260805000002"},
        ],
    }
    response_text = json.dumps(response, ensure_ascii=False, indent=2)
    (batch_dir / "response.json").write_text(response_text, encoding="utf-8")
    digest = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
    metadata = {
        "correlation_id": corr,
        "fetched_at": now_iso(),
        "sha256": digest,
        "demo_mode": True,
        "external_boundary": boundary,
    }
    (batch_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    def mutate(s):
        s["dart"]["last_collect"] = metadata
        s["dart"]["saved_batches"].append(str(batch_dir))

    update_state(mutate)
    result = ServiceResult(
        ResultStatus.SUCCESS,
        "DART_COLLECT_OK",
        "OpenDART 데모 원본을 저장했습니다.",
        {"count": 2, "saved_path": str(batch_dir), **metadata},
    )
    _audit(corr, "DART_COLLECTION", result)
    return result


def dart_replay(corr: str) -> ServiceResult:
    state = read_state()
    batches = state["dart"].get("saved_batches", [])
    if not batches:
        result = ServiceResult(ResultStatus.BLOCKED, "NO_SAVED_DART_BATCH", "재현할 저장본이 없습니다.")
    else:
        path = Path(batches[-1]) / "response.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            normalized = [
                {
                    "company": item["corp_name"],
                    "title": item["report_nm"],
                    "receipt_no": item["rcept_no"],
                }
                for item in raw.get("list", [])
            ]
            canonical = json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            normalized_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            result = ServiceResult(
                ResultStatus.SUCCESS,
                "DART_REPLAY_OK",
                "저장본으로 공시 정규화를 재현했습니다.",
                {
                    "source_path": str(path),
                    "normalized": normalized,
                    "normalized_hash": normalized_hash,
                    "network_called": False,
                },
            )
        except Exception as exc:
            result = ServiceResult(ResultStatus.ERROR, "DART_REPLAY_ERROR", str(exc))
    _audit(corr, "DART_REPLAY", result)
    return result


def inject_reconciliation_mode(corr: str, mode: str) -> ServiceResult:
    mode = mode.upper()
    if mode not in {"MATCH", "MISMATCH", "UNKNOWN"}:
        result = ServiceResult(ResultStatus.ERROR, "INVALID_RECONCILIATION_MODE", "MATCH, MISMATCH, UNKNOWN만 허용합니다.")
    else:
        update_state(lambda s: s["demo"].update({"reconciliation_mode": mode}))
        result = ServiceResult(ResultStatus.SUCCESS, "RECONCILIATION_MODE_SET", f"다음 대사 모드를 {mode}로 설정했습니다.", {"mode": mode})
    _audit(corr, "DEMO_RECONCILIATION_MODE", result, actor=OWNER_ACTOR_ID)
    return result


def reconcile(corr: str) -> ServiceResult:
    record_external_call("kis_reconciliation_account")
    record_external_call("kis_reconciliation_orders")
    state = read_state()
    mode = state["demo"].get("reconciliation_mode", "MATCH")

    if mode == "MISMATCH":
        differences = [{
            "category": "POSITION",
            "key": "005930",
            "ledger_value": 1,
            "broker_value": 2,
            "severity": "BLOCKING",
            "message": "내부 원장 1주, 증권사 2주",
        }]
        status = "MISMATCH"
        message = "포지션 수량 불일치 1건을 발견했습니다."
        result_status = ResultStatus.BLOCKED
        code = "RECONCILIATION_MISMATCH"
        halt_reason = "RECONCILIATION_MISMATCH"
    elif mode == "UNKNOWN":
        differences = [{
            "category": "BROKER_DATA",
            "key": "orders",
            "ledger_value": "AVAILABLE",
            "broker_value": "UNAVAILABLE",
            "severity": "BLOCKING",
            "message": "증권사 주문·체결 상태를 확인할 수 없습니다.",
        }]
        status = "UNKNOWN"
        message = "대사에 필요한 증권사 상태를 확인할 수 없습니다."
        result_status = ResultStatus.UNKNOWN
        code = "RECONCILIATION_UNKNOWN"
        halt_reason = "RECONCILIATION_UNKNOWN"
    else:
        differences = []
        status = "MATCH"
        message = "내부 원장과 증권사 계좌가 일치합니다."
        result_status = ResultStatus.SUCCESS
        code = "RECONCILIATION_MATCH"
        halt_reason = None

    def mutate(s):
        s["last_reconciliation"] = {
            "status": status,
            "checked_at": now_iso(),
            "message": message,
            "differences": differences,
        }
        # 대사를 다시 했으므로 이전 전체 점검은 더 이상 최신이 아니다.
        s["last_full_check"]["status"] = "UNKNOWN"
        s["last_full_check"]["message"] = "최근 대사 이후 전체 점검이 필요합니다."
        s["last_full_check"]["blockers"] = ["STALE_AFTER_RECONCILIATION"]
        if status != "MATCH":
            s["kill_switch"].update({
                "state": "ON",
                "changed_at": now_iso(),
                "changed_by": "reconciliation_worker",
                "reason": halt_reason,
            })
            s["gate"].update({
                "state": "HALTED",
                "changed_at": now_iso(),
                "changed_by": "reconciliation_worker",
                "reason": halt_reason,
            })
            s["active_halt"] = {
                "cause": halt_reason,
                "triggered_at": now_iso(),
                "triggered_by": "reconciliation_worker",
                "resolved": False,
            }
        elif (s.get("active_halt") or {}).get("cause") in {
            "RECONCILIATION_MISMATCH", "RECONCILIATION_UNKNOWN"
        }:
            s["active_halt"]["resolved"] = True
            s["active_halt"]["resolved_at"] = now_iso()

    state = update_state(mutate)
    result = ServiceResult(
        result_status,
        code,
        message,
        state["last_reconciliation"],
        None if status == "MATCH" else "원인을 확인하고 복구 후 대사를 다시 실행하십시오.",
    )
    _audit(corr, "RECONCILIATION", result)
    if status != "MATCH":
        _audit(
            corr,
            "KILL_SWITCH_CHANGED",
            ServiceResult(ResultStatus.SUCCESS, "KILL_SWITCH_ON", "대사 문제로 킬 스위치를 켰습니다.", state["kill_switch"]),
            actor="reconciliation_worker",
        )
        _audit(
            corr,
            "GATE_CHANGED",
            ServiceResult(ResultStatus.BLOCKED, "GATE_HALTED", "대사 문제로 거래 게이트를 정지했습니다.", state["gate"]),
            actor="reconciliation_worker",
        )
    return result


def repair_demo(corr: str, confirmation: str) -> ServiceResult:
    if confirmation != "CONFIRM":
        result = ServiceResult(ResultStatus.BLOCKED, "CONFIRMATION_MISMATCH", "CONFIRM 문구가 필요합니다.")
    else:
        def mutate(s):
            s["demo"]["reconciliation_mode"] = "MATCH"
            s["last_reconciliation"] = {
                "status": "UNKNOWN",
                "checked_at": now_iso(),
                "message": "복구 후 대사를 다시 실행해야 합니다.",
                "differences": [],
            }
            s["last_full_check"]["status"] = "UNKNOWN"
            s["last_full_check"]["blockers"] = ["RECONCILIATION_REQUIRED"]

        update_state(mutate)
        result = ServiceResult(ResultStatus.SUCCESS, "DEMO_REPAIR_OK", "데모 원장 복구를 적용했습니다. 대사를 다시 실행하십시오.")
    _audit(corr, "DEMO_REPAIR", result, actor=OWNER_ACTOR_ID)
    return result


def seed_open_order(corr: str) -> ServiceResult:
    order_id = "demo_order_" + uuid4().hex[:8]

    def mutate(s):
        s["orders"].append({
            "order_id": order_id,
            "symbol": "005930",
            "quantity": 1,
            "state": "SUBMITTED",
            "created_at": now_iso(),
            "demo_mode": True,
        })

    update_state(mutate)
    result = ServiceResult(ResultStatus.SUCCESS, "DEMO_OPEN_ORDER_SEEDED", "미체결 데모 주문을 추가했습니다.", {"order_id": order_id})
    _audit(corr, "DEMO_ORDER_SEEDED", result, actor=OWNER_ACTOR_ID)
    return result


def seed_unknown_order(corr: str) -> ServiceResult:
    order_id = "demo_unknown_" + uuid4().hex[:8]

    def mutate(s):
        s["orders"].append({
            "order_id": order_id,
            "symbol": "005930",
            "quantity": 1,
            "state": "UNKNOWN",
            "created_at": now_iso(),
            "demo_mode": True,
        })

    update_state(mutate)
    result = ServiceResult(ResultStatus.SUCCESS, "DEMO_UNKNOWN_ORDER_SEEDED", "UNKNOWN 데모 주문을 추가했습니다.", {"order_id": order_id})
    _audit(corr, "DEMO_UNKNOWN_ORDER_SEEDED", result, actor=OWNER_ACTOR_ID)
    return result


def cancel_open_orders(corr: str, confirmation: str) -> ServiceResult:
    if confirmation != "CONFIRM":
        result = ServiceResult(ResultStatus.BLOCKED, "CONFIRMATION_MISMATCH", "CONFIRM 문구가 필요합니다.")
    else:
        boundary = record_external_call("kis_cancel_open_orders")
        state = read_state()
        target_ids = [o["order_id"] for o in _open_orders(state)]

        def mutate(s):
            for order in s["orders"]:
                if order.get("order_id") in target_ids:
                    order["state"] = "CANCELED"
                    order["canceled_at"] = now_iso()

        state = update_state(mutate)
        result = ServiceResult(
            ResultStatus.SUCCESS,
            "OPEN_ORDERS_CANCELED",
            f"미체결 주문 {len(target_ids)}건을 취소했습니다.",
            {"canceled_order_ids": target_ids, "external_boundary": boundary, "gate": state["gate"]},
        )
    _audit(corr, "OPEN_ORDERS_CANCEL", result, actor=OWNER_ACTOR_ID)
    return result


def order_submit_out_of_scope(corr: str) -> ServiceResult:
    """Console V1은 주문 제출을 포함하지 않는다는 실행 계약."""
    result = ServiceResult(
        ResultStatus.BLOCKED,
        "OUT_OF_SCOPE_CONSOLE_V1",
        "Console V1에는 주문 제출 기능이 없습니다. 주문 타임아웃 복구는 다음 단계에서 구현합니다.",
        {"automatic_retry": False, "order_submitted": False},
    )
    _audit(corr, "ORDER_SUBMIT_REJECTED", result)
    return result


def kill_status(corr: str) -> ServiceResult:
    state = read_state()
    recent = [
        item for item in read_recent(100)
        if item.get("event") == "KILL_SWITCH_CHANGED"
    ][-20:]
    result = ServiceResult(ResultStatus.SUCCESS, "KILL_STATUS_OK", "킬 스위치 상태를 조회했습니다.", {
        "current": state["kill_switch"],
        "active_halt": state.get("active_halt"),
        "history": recent,
    })
    _audit(corr, "KILL_STATUS", result)
    return result


def halt_trading(corr: str, reason: str) -> ServiceResult:
    """감사 로그가 고장 나도 안전 정지는 우선 수행한다."""
    reason = reason.strip() or "수동 비상 정지"

    def mutate(s):
        s["kill_switch"].update({
            "state": "ON",
            "changed_at": now_iso(),
            "changed_by": OWNER_ACTOR_ID,
            "reason": reason,
        })
        s["gate"].update({
            "state": "HALTED",
            "changed_at": now_iso(),
            "changed_by": OWNER_ACTOR_ID,
            "reason": reason,
        })
        s["active_halt"] = {
            "cause": "MANUAL_EMERGENCY",
            "reason": reason,
            "triggered_at": now_iso(),
            "triggered_by": OWNER_ACTOR_ID,
            "resolved": False,
        }
        s["last_full_check"]["status"] = "UNKNOWN"
        s["last_full_check"]["blockers"] = ["HALT_OCCURRED"]

    state = update_state(mutate)
    result = ServiceResult(ResultStatus.SUCCESS, "TRADING_HALTED", "거래를 정지하고 신규 위험을 차단했습니다.", {
        "cause": "MANUAL_EMERGENCY",
        "reason": reason,
        "triggered_at": state["kill_switch"]["changed_at"],
        "triggered_by": OWNER_ACTOR_ID,
        "kill_switch": state["kill_switch"],
        "gate": state["gate"],
    })
    persisted = _audit(corr, "KILL_SWITCH_CHANGED", result, actor=OWNER_ACTOR_ID)
    _audit(
        corr,
        "GATE_CHANGED",
        ServiceResult(ResultStatus.BLOCKED, "GATE_HALTED", "수동 비상 정지로 게이트가 HALTED가 됐습니다.", state["gate"]),
        actor=OWNER_ACTOR_ID,
    )
    result.payload["audit_persisted"] = persisted
    return result


def resume_trading(corr: str, confirmation: str, reason: str) -> ServiceResult:
    # GUI 표시값이 아니라 명령 실행 시점의 권위 상태를 다시 읽는다.
    state = read_state()
    audit_status, audit_message = health(check_write=True)
    full_ok, full_message = _full_check_valid_for_current_state(state)

    if confirmation != "RESUME TRADING":
        result = ServiceResult(ResultStatus.BLOCKED, "CONFIRMATION_MISMATCH", "RESUME TRADING 문구가 필요합니다.")
    elif state["gate"]["state"] != "HALTED" or state["kill_switch"]["state"] != "ON":
        result = ServiceResult(ResultStatus.BLOCKED, "NOT_HALTED", "현재 정지 상태가 아닙니다.")
    elif audit_status not in {"HEALTHY", "DEGRADED"}:
        result = ServiceResult(ResultStatus.BLOCKED, "AUDIT_UNHEALTHY", audit_message)
    elif state["last_reconciliation"]["status"] != "MATCH":
        result = ServiceResult(ResultStatus.BLOCKED, "RECONCILIATION_NOT_MATCH", "최근 대사가 MATCH가 아닙니다.")
    elif _unknown_orders(state):
        result = ServiceResult(ResultStatus.BLOCKED, "UNKNOWN_ORDERS", "미해결 UNKNOWN 주문이 있습니다.")
    elif not full_ok:
        result = ServiceResult(ResultStatus.BLOCKED, "FULL_CHECK_NOT_CURRENT", full_message)
    elif not reason.strip():
        result = ServiceResult(ResultStatus.BLOCKED, "RESUME_REASON_REQUIRED", "재가동 사유를 입력하십시오.")
    else:
        try:
            probe_writable()
            append_audit(
                event="TRADING_RESUME_PREPARE",
                status="SUCCESS",
                correlation_id=corr,
                actor=OWNER_ACTOR_ID,
                message="재가동 전 권위 상태를 다시 확인했습니다.",
                payload={
                    "reconciliation": state["last_reconciliation"],
                    "full_check": state["last_full_check"],
                },
            )

            def mutate(s):
                s["kill_switch"].update({
                    "state": "OFF",
                    "changed_at": now_iso(),
                    "changed_by": OWNER_ACTOR_ID,
                    "reason": reason.strip(),
                })
                s["gate"].update({
                    "state": "OPEN",
                    "changed_at": now_iso(),
                    "changed_by": OWNER_ACTOR_ID,
                    "reason": "RESUME TRADING 확인: " + reason.strip(),
                })
                if s.get("active_halt"):
                    s["active_halt"]["resolved"] = True
                    s["active_halt"]["resumed_at"] = now_iso()
                    s["active_halt"]["resume_reason"] = reason.strip()

            state = update_state(mutate)
            result = ServiceResult(ResultStatus.SUCCESS, "TRADING_RESUMED", "사람 확인 후 거래를 재가동했습니다.", {
                "kill_switch": state["kill_switch"],
                "gate": state["gate"],
            })
            try:
                _audit(corr, "TRADING_RESUME", result, actor=OWNER_ACTOR_ID, required=True)
            except OSError as exc:
                def rollback(s):
                    s["kill_switch"].update({
                        "state": "ON",
                        "changed_at": now_iso(),
                        "changed_by": "audit_guard",
                        "reason": "감사 기록 실패로 재가동 롤백",
                    })
                    s["gate"].update({
                        "state": "HALTED",
                        "changed_at": now_iso(),
                        "changed_by": "audit_guard",
                        "reason": "감사 기록 실패로 재가동 롤백",
                    })
                update_state(rollback)
                result = ServiceResult(ResultStatus.ERROR, "AUDIT_COMMIT_FAILED", str(exc))
        except OSError as exc:
            result = ServiceResult(ResultStatus.BLOCKED, "AUDIT_UNHEALTHY", str(exc))

    if result.code not in {"TRADING_RESUMED", "AUDIT_COMMIT_FAILED"}:
        _audit(corr, "TRADING_RESUME", result, actor=OWNER_ACTOR_ID)
    return result


def inject_audit_failure(corr: str, enabled: bool) -> ServiceResult:
    # 이 시험 명령은 감사 저장소 자체를 고장 내므로 감사 이벤트를 남기지 않는다.
    set_failure_injection(enabled)
    status, message = health(check_write=True)
    update_state(lambda s: s.update({"audit_health": status}))
    return ServiceResult(
        ResultStatus.SUCCESS,
        "AUDIT_FAILURE_ENABLED" if enabled else "AUDIT_FAILURE_DISABLED",
        "감사 로그 쓰기 실패를 주입했습니다." if enabled else "감사 로그 쓰기 실패 주입을 해제했습니다.",
        {"enabled": enabled, "health": status, "message": message},
    )


def audit_health(corr: str) -> ServiceResult:
    status, message = health(check_write=True)
    update_state(lambda s: s.update({"audit_health": status}))
    rs = ResultStatus.SUCCESS if status in {"HEALTHY", "DEGRADED"} else ResultStatus.UNKNOWN
    result = ServiceResult(rs, "AUDIT_HEALTH_" + status, message, {"health": status})
    _audit(corr, "AUDIT_HEALTH", result)
    return result


def audit_recent(corr: str, limit: int) -> ServiceResult:
    result = ServiceResult(ResultStatus.SUCCESS, "AUDIT_RECENT_OK", "최근 감사 기록을 조회했습니다.", {
        "records": read_recent(limit=max(1, min(limit, 500))),
    })
    _audit(corr, "AUDIT_RECENT", result)
    return result


def audit_trace(corr: str, target_correlation_id: str) -> ServiceResult:
    if not target_correlation_id.strip():
        result = ServiceResult(ResultStatus.ERROR, "TRACE_ID_REQUIRED", "추적할 correlation_id를 입력하십시오.")
    else:
        records = trace(target_correlation_id.strip())
        result = ServiceResult(ResultStatus.SUCCESS, "AUDIT_TRACE_OK", f"추적 기록 {len(records)}건을 조회했습니다.", {
            "target_correlation_id": target_correlation_id.strip(),
            "records": records,
        })
    _audit(corr, "AUDIT_TRACE", result)
    return result
