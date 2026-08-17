from __future__ import annotations

from kstock.console_app import symbol_from_choice, watch_choices


def test_watch_choices_include_name_interest_group_and_holding() -> None:
    choices = watch_choices({
        "members": [
            {
                "symbol": "000660",
                "name": "SK하이닉스",
                "sources": ["KIS_INTEREST", "HOLDING"],
                "interest_groups": ["반도체"],
                "held_quantity": 3,
            },
            {
                "symbol": "035420",
                "name": "NAVER",
                "sources": ["KIS_INTEREST"],
                "interest_groups": [],
                "held_quantity": 0,
            },
        ]
    })

    assert [symbol for _label, symbol in choices] == ["000660", "035420"]
    assert "SK하이닉스" in choices[0][0]
    assert "관심: 반도체" in choices[0][0]
    assert "보유 3주" in choices[0][0]
    assert "KIS 관심" in choices[1][0]


def test_symbol_from_choice_uses_mapping_and_allows_manual_input() -> None:
    label = "000660  SK하이닉스  [관심: 반도체]"
    assert symbol_from_choice(label, {label: "000660"}) == "000660"
    assert symbol_from_choice("005930  삼성전자") == "005930"
    assert symbol_from_choice("AAPL") == "AAPL"


def test_watch_choices_ignore_invalid_and_duplicate_members() -> None:
    choices = watch_choices({
        "members": [
            {"symbol": "005930", "name": "삼성전자"},
            {"symbol": "005930", "name": "중복"},
            {"symbol": "", "name": "빈 코드"},
            {"symbol": "000660", "name": "SK하이닉스", "held_quantity": "invalid"},
            "invalid",
        ]
    })

    assert choices == (
        ("005930  삼성전자", "005930"),
        ("000660  SK하이닉스", "000660"),
    )
