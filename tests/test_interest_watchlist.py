from __future__ import annotations

from dataclasses import dataclass

from kstock.broker.interest import (
    InterestGroup,
    InterestStock,
    KisInterestClient,
    normalize_groups,
    normalize_stocks,
)
from kstock.interest_services import sync_interest_watchlist
from kstock.models import ResultStatus
from kstock.state_store import read_state, update_state
from kstock.watch.universe import build_watch_universe


@dataclass
class FakeHttpConfig:
    hts_user_id: str = "hsc_test"


class FakeHttp:
    def __init__(self):
        self.config = FakeHttpConfig()
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def get(self, *, path, tr_id, params):
        self.calls.append((path, tr_id, dict(params)))
        if tr_id == "HHKCM113004C7":
            return {"rt_cd": "0", "output2": [
                {"inter_grp_code": "001", "inter_grp_name": "반도체", "data_rank": "1"},
                {"inter_grp_code": "002", "inter_grp_name": "관심2", "data_rank": "2"},
            ]}
        group = params["INTER_GRP_CODE"]
        if group == "001":
            return {"rt_cd": "0", "output2": [
                {"jong_code": "005930", "hts_kor_isnm": "삼성전자", "exch_code": "KRX"},
                {"jong_code": "000660", "hts_kor_isnm": "SK하이닉스", "exch_code": "KRX"},
            ]}
        return {"rt_cd": "0", "output2": [
            {"jong_code": "005930", "hts_kor_isnm": "삼성전자", "exch_code": "KRX"},
            {"jong_code": "035420", "hts_kor_isnm": "NAVER", "exch_code": "KRX"},
        ]}


def test_group_normalization_uses_kis_fields():
    groups = normalize_groups([
        {"inter_grp_code": "001", "inter_grp_name": "반도체", "data_rank": "1"},
    ])
    assert groups == (InterestGroup("001", "반도체", "1"),)


def test_stock_normalization_uses_kis_fields():
    stocks = normalize_stocks([
        {"jong_code": "005930", "hts_kor_isnm": "삼성전자", "exch_code": "KRX", "memo": "핵심"},
    ], group_code="001", group_name="반도체")
    assert stocks[0].symbol == "005930"
    assert stocks[0].name == "삼성전자"
    assert stocks[0].group_names == ("반도체",)


def test_all_interest_groups_are_deduplicated_by_symbol():
    client = KisInterestClient(FakeHttp())
    stocks = client.all_stocks()
    by_symbol = {s.symbol: s for s in stocks}
    assert set(by_symbol) == {"000660", "005930", "035420"}
    assert by_symbol["005930"].group_names == ("반도체", "관심2")


def test_watch_universe_is_holdings_union_interest():
    interest = [InterestStock(symbol="000660", name="SK하이닉스", group_names=("반도체",))]
    universe = build_watch_universe(
        environment="PAPER",
        account_ref="PAPER_PRIMARY",
        positions=[{"symbol": "005930", "name": "삼성전자", "quantity": 10}],
        interest_stocks=interest,
    )
    assert universe.symbols == ("000660", "005930")
    samsung = next(m for m in universe.members if m.symbol == "005930")
    assert samsung.sources == ("HOLDING",)
    assert samsung.held_quantity == 10


def test_symbol_in_holdings_and_interest_merges_sources():
    universe = build_watch_universe(
        environment="PAPER",
        account_ref="PAPER_PRIMARY",
        positions=[{"symbol": "005930", "name": "삼성전자", "quantity": 10}],
        interest_stocks=[InterestStock(symbol="005930", name="삼성전자", group_names=("반도체",))],
    )
    member = universe.members[0]
    assert member.sources == ("HOLDING", "KIS_INTEREST")
    assert member.interest_groups == ("반도체",)


def test_interest_sync_persists_watch_universe(tmp_path, monkeypatch):
    monkeypatch.setenv("KSTOCK_CONSOLE_DATA", str(tmp_path))
    update_state(lambda s: s.update({"account_snapshot": {
        "positions": [{"symbol": "051910", "name": "LG화학", "quantity": 2}],
    }}))
    client = KisInterestClient(FakeHttp())
    result = sync_interest_watchlist("corr_interest", "PAPER", client=client)
    assert result.status is ResultStatus.SUCCESS
    state = read_state()
    assert state["interest_snapshot"]["count"] == 3
    assert set(state["watch_universe"]["symbols"]) == {"000660", "005930", "035420", "051910"}


def test_interest_group_filter_is_applied():
    client = KisInterestClient(FakeHttp())
    stocks = client.all_stocks(only_group_code="001")
    assert {s.symbol for s in stocks} == {"005930", "000660"}


def test_watch_layer_does_not_import_broker():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "kstock" / "watch" / "universe.py").read_text(encoding="utf-8")
    assert "kstock.broker" not in text
    assert "from ..broker" not in text


def test_command_registry_exposes_interest_read_commands():
    from kstock.console_commands import COMMANDS
    assert COMMANDS["interest_groups"].risk_class.value == "R0"
    assert COMMANDS["interest_sync"].risk_class.value == "R0"
    assert COMMANDS["interest_show"].risk_class.value == "R0"
