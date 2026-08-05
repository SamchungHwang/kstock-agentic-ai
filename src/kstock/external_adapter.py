from __future__ import annotations

from typing import Any

from .env_config import resolve_kis_credentials
from .state_store import now_iso, update_state


def record_external_call(name: str) -> dict[str, Any]:
    """실제 네트워크 대신 외부 경계 호출을 계측하는 DEMO 어댑터.

    자격증명은 .env에서 읽지만 비밀값은 반환하거나 감사 로그에 남기지 않는다.
    Console V1 실습은 네트워크 대신 외부 경계 호출 횟수만 계측한다.
    """

    def mutate(state):
        calls = state["metrics"].setdefault("external_calls", {})
        calls[name] = int(calls.get(name, 0)) + 1

    state = update_state(mutate)
    return {
        "adapter": "DEMO_EXTERNAL_BOUNDARY",
        "name": name,
        "called_at": now_iso(),
        "count": state["metrics"]["external_calls"][name],
        "network_called": False,
    }


def probe_kis_environment(environment: str) -> dict[str, Any]:
    creds = resolve_kis_credentials(environment)
    errors = creds.validation_errors()
    return {
        "name": "kis_environment",
        "status": "PASS" if not errors else "FAIL",
        "credentials": creds.safe_summary(),
        "network_called": False,
    }


def probe_full_check_boundaries(environment: str) -> list[dict[str, Any]]:
    return [
        probe_kis_environment(environment),
        record_external_call("kis_auth_probe"),
        record_external_call("kis_account_probe"),
        record_external_call("kis_orders_probe"),
        record_external_call("opendart_probe"),
    ]
