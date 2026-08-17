from __future__ import annotations

import hashlib

from kstock.audit_store import append_audit
from kstock.broker.interest import KisInterestClient
from kstock.broker.kis_readonly import KisReadOnlyError
from kstock.models import ResultStatus
from kstock.state_store import current_account_ref, now_iso, read_state, require_runtime_environment, update_state
from kstock.watch.universe import build_watch_universe

from .demo_services import ServiceResult


INTEREST_CONFIG_ACTION = (
    "한국투자 HTS 로그인 ID를 .env의 KIS_HTS_ID에 설정하십시오. "
    "KIS_HTS_USER_ID·KIS_USER_ID 등 기존 키도 지원합니다."
)


def _masked_hts_user_id(value: str) -> str:
    if len(value) <= 3:
        return "*" * len(value)
    return value[:2] + "*" * max(1, len(value) - 3) + value[-1:]


def _audit(corr: str, event: str, result: ServiceResult) -> None:
    try:
        append_audit(
            event=event,
            status=result.status.value,
            correlation_id=corr,
            actor="OWNER",
            message=result.message,
            payload={"code": result.code, "count": result.payload.get("count", 0)},
        )
    except OSError:
        pass


def interest_groups_query(
    corr: str,
    environment: str,
    *,
    client: KisInterestClient | None = None,
) -> ServiceResult:
    environment = require_runtime_environment(environment)
    try:
        interest = client or KisInterestClient.for_environment(environment)
        groups = interest.groups()
        payload = {
            "environment": environment,
            "account_ref": current_account_ref(),
            "hts_user_id": _masked_hts_user_id(interest.hts_user_id),
            "count": len(groups),
            "groups": [
                {"group_code": g.group_code, "group_name": g.group_name, "data_rank": g.data_rank}
                for g in groups
            ],
        }
        result = ServiceResult(ResultStatus.SUCCESS, "INTEREST_GROUPS_OK", "KIS 관심종목 그룹을 조회했습니다.", payload)
    except (KisReadOnlyError, ValueError) as exc:
        result = ServiceResult(
            ResultStatus.BLOCKED,
            "INTEREST_GROUPS_UNAVAILABLE",
            str(exc),
            {},
            INTEREST_CONFIG_ACTION,
        )
    _audit(corr, "INTEREST_GROUPS_QUERY", result)
    return result


def sync_interest_watchlist(
    corr: str,
    environment: str,
    *,
    group_code: str = "",
    client: KisInterestClient | None = None,
) -> ServiceResult:
    environment = require_runtime_environment(environment)
    try:
        interest = client or KisInterestClient.for_environment(environment)
        stocks = interest.all_stocks(only_group_code=group_code.strip())
        state = read_state()
        account_snapshot = state.get("account_snapshot") or {}
        positions = account_snapshot.get("positions") or []
        universe = build_watch_universe(
            environment=environment,
            account_ref=current_account_ref(),
            positions=positions,
            interest_stocks=stocks,
        )
        interest_snapshot = {
            "source": "KIS_HTS_INTEREST",
            "hts_user_id": _masked_hts_user_id(interest.hts_user_id),
            "group_code": group_code.strip() or "ALL",
            "fetched_at": now_iso(),
            "count": len(stocks),
            "stocks": [
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "exchange_code": s.exchange_code,
                    "memo": s.memo,
                    "group_codes": list(s.group_codes),
                    "group_names": list(s.group_names),
                }
                for s in stocks
            ],
        }
        watch_dict = universe.to_dict()
        watch_hash = hashlib.sha256(
            "|".join(watch_dict["symbols"]).encode("utf-8")
        ).hexdigest()
        watch_dict["watch_universe_hash"] = watch_hash

        update_state(lambda s: s.update({
            "interest_snapshot": interest_snapshot,
            "watch_universe": watch_dict,
        }))

        holding_count = sum(1 for m in universe.members if "HOLDING" in m.sources)
        interest_count = sum(1 for m in universe.members if "KIS_INTEREST" in m.sources)
        payload = {
            "environment": environment,
            "account_ref": current_account_ref(),
            "count": len(universe.members),
            "interest_count": interest_count,
            "holding_count": holding_count,
            "watch_universe_hash": watch_hash,
            "symbols": list(universe.symbols),
            "members": watch_dict["members"],
            "account_snapshot_included": bool(account_snapshot),
        }
        result = ServiceResult(
            ResultStatus.SUCCESS,
            "INTEREST_WATCHLIST_SYNCED",
            f"보유종목과 KIS 관심종목을 합쳐 Watch 대상 {len(universe.members)}종목을 만들었습니다.",
            payload,
            None if account_snapshot else "보유종목까지 포함하려면 먼저 계좌 조회를 실행하십시오.",
        )
    except (KisReadOnlyError, ValueError) as exc:
        result = ServiceResult(
            ResultStatus.BLOCKED,
            "INTEREST_WATCHLIST_UNAVAILABLE",
            str(exc),
            {},
            INTEREST_CONFIG_ACTION,
        )
    _audit(corr, "INTEREST_WATCHLIST_SYNC", result)
    return result


def current_watch_universe(corr: str) -> ServiceResult:
    state = read_state()
    watch = state.get("watch_universe")
    if not watch:
        result = ServiceResult(
            ResultStatus.BLOCKED,
            "WATCH_UNIVERSE_NOT_READY",
            "아직 관심종목을 동기화하지 않았습니다.",
            {},
            "interest sync를 먼저 실행하십시오.",
        )
    else:
        payload = dict(watch)
        payload["count"] = len(payload.get("members", []))
        result = ServiceResult(ResultStatus.SUCCESS, "WATCH_UNIVERSE_OK", "현재 Watch 대상을 조회했습니다.", payload)
    _audit(corr, "WATCH_UNIVERSE_SHOW", result)
    return result
