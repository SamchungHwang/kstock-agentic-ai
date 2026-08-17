from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class WatchUniverseMember:
    symbol: str
    name: str
    sources: tuple[str, ...]
    interest_groups: tuple[str, ...] = ()
    held_quantity: int = 0


@dataclass(frozen=True, slots=True)
class WatchUniverseSnapshot:
    environment: str
    account_ref: str
    as_of: str
    members: tuple[WatchUniverseMember, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(member.symbol for member in self.members)

    def to_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "account_ref": self.account_ref,
            "as_of": self.as_of,
            "symbols": list(self.symbols),
            "members": [asdict(member) for member in self.members],
        }


def build_watch_universe(
    *,
    environment: str,
    account_ref: str,
    positions: Sequence[Mapping[str, object]],
    interest_stocks: Iterable[object],
    as_of: datetime | None = None,
) -> WatchUniverseSnapshot:
    """보유종목과 KIS 관심종목의 합집합을 만든다.

    관심종목에서 제거해도 현재 보유 중인 종목은 계속 감시해야 하므로 HOLDING은
    항상 포함한다. Watch 계층은 Broker를 import하지 않고 정규화된 데이터만 받는다.
    """
    merged: dict[str, dict[str, object]] = {}

    for position in positions:
        symbol = str(position.get("symbol", "")).strip()
        qty = int(position.get("quantity", 0) or 0)
        if not symbol or qty == 0:
            continue
        merged[symbol] = {
            "name": str(position.get("name", "")).strip(),
            "sources": ["HOLDING"],
            "groups": [],
            "held_quantity": qty,
        }

    for stock in interest_stocks:
        symbol = str(getattr(stock, "symbol", "")).strip()
        if not symbol:
            continue
        row = merged.setdefault(symbol, {
            "name": "",
            "sources": [],
            "groups": [],
            "held_quantity": 0,
        })
        if "KIS_INTEREST" not in row["sources"]:
            row["sources"].append("KIS_INTEREST")
        name = str(getattr(stock, "name", "")).strip()
        if name and not row["name"]:
            row["name"] = name
        for group_name in getattr(stock, "group_names", ()):
            if group_name and group_name not in row["groups"]:
                row["groups"].append(group_name)

    members = tuple(
        WatchUniverseMember(
            symbol=symbol,
            name=str(values["name"]),
            sources=tuple(values["sources"]),
            interest_groups=tuple(values["groups"]),
            held_quantity=int(values["held_quantity"]),
        )
        for symbol, values in sorted(merged.items())
    )
    stamp = (as_of or datetime.now().astimezone()).isoformat(timespec="seconds")
    return WatchUniverseSnapshot(
        environment=environment,
        account_ref=account_ref,
        as_of=stamp,
        members=members,
    )
