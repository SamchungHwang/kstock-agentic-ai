from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .kis_readonly import KisReadOnlyConfig, KisReadOnlyHttpClient


GROUP_LIST_PATH = "/uapi/domestic-stock/v1/quotations/intstock-grouplist"
GROUP_LIST_TR_ID = "HHKCM113004C7"
STOCK_LIST_PATH = "/uapi/domestic-stock/v1/quotations/intstock-stocklist-by-group"
STOCK_LIST_TR_ID = "HHKCM113004C6"


@dataclass(frozen=True, slots=True)
class InterestGroup:
    group_code: str
    group_name: str
    data_rank: str = ""


@dataclass(frozen=True, slots=True)
class InterestStock:
    symbol: str
    name: str
    exchange_code: str = ""
    memo: str = ""
    group_codes: tuple[str, ...] = ()
    group_names: tuple[str, ...] = ()


class KisInterestClient:
    """KIS HTS/MTS 관심종목을 읽는 조회 전용 facade."""

    def __init__(self, http: KisReadOnlyHttpClient) -> None:
        self.http = http

    @classmethod
    def for_environment(cls, environment: str) -> "KisInterestClient":
        return cls(KisReadOnlyHttpClient(KisReadOnlyConfig.from_environment(environment)))

    @property
    def hts_user_id(self) -> str:
        return self.http.config.hts_user_id

    def groups(self) -> tuple[InterestGroup, ...]:
        payload = self.http.get(
            path=GROUP_LIST_PATH,
            tr_id=GROUP_LIST_TR_ID,
            params={
                "TYPE": "1",
                "FID_ETC_CLS_CODE": "00",
                "USER_ID": self.hts_user_id,
            },
        )
        return normalize_groups(payload.get("output2", []))

    def stocks(self, group: InterestGroup) -> tuple[InterestStock, ...]:
        payload = self.http.get(
            path=STOCK_LIST_PATH,
            tr_id=STOCK_LIST_TR_ID,
            params={
                "TYPE": "1",
                "USER_ID": self.hts_user_id,
                "INTER_GRP_CODE": group.group_code,
                "FID_ETC_CLS_CODE": "4",
                "DATA_RANK": "",
                "INTER_GRP_NAME": group.group_name,
                "HTS_KOR_ISNM": "",
                "CNTG_CLS_CODE": "",
            },
        )
        return normalize_stocks(
            payload.get("output2", []),
            group_code=group.group_code,
            group_name=group.group_name,
        )

    def all_stocks(self, *, only_group_code: str = "") -> tuple[InterestStock, ...]:
        groups = self.groups()
        if only_group_code:
            groups = tuple(g for g in groups if g.group_code == only_group_code)
            if not groups:
                raise ValueError(f"INTEREST_GROUP_NOT_FOUND:{only_group_code}")

        merged: dict[str, InterestStock] = {}
        for group in groups:
            for stock in self.stocks(group):
                prior = merged.get(stock.symbol)
                if prior is None:
                    merged[stock.symbol] = stock
                    continue
                merged[stock.symbol] = InterestStock(
                    symbol=stock.symbol,
                    name=stock.name or prior.name,
                    exchange_code=stock.exchange_code or prior.exchange_code,
                    memo=stock.memo or prior.memo,
                    group_codes=_merge_tuple(prior.group_codes, stock.group_codes),
                    group_names=_merge_tuple(prior.group_names, stock.group_names),
                )
        return tuple(sorted(merged.values(), key=lambda item: item.symbol))


def normalize_groups(rows: Any) -> tuple[InterestGroup, ...]:
    if not isinstance(rows, list):
        return ()
    groups: list[InterestGroup] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("inter_grp_code", "")).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        groups.append(InterestGroup(
            group_code=code,
            group_name=str(raw.get("inter_grp_name", "")).strip(),
            data_rank=str(raw.get("data_rank", "")).strip(),
        ))
    return tuple(groups)


def normalize_stocks(rows: Any, *, group_code: str, group_name: str) -> tuple[InterestStock, ...]:
    if not isinstance(rows, list):
        return ()
    stocks: list[InterestStock] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("jong_code", "")).strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        stocks.append(InterestStock(
            symbol=symbol,
            name=str(raw.get("hts_kor_isnm", "")).strip(),
            exchange_code=str(raw.get("exch_code", "")).strip(),
            memo=str(raw.get("memo", "")).strip(),
            group_codes=(group_code,),
            group_names=(group_name,),
        ))
    return tuple(stocks)


def _merge_tuple(left: Iterable[str], right: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*(v for v in left if v), *(v for v in right if v)]))
