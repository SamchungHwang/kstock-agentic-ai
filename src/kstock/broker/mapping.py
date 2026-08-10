from __future__ import annotations


def map_side(side: str) -> str:
    value = side.upper()
    if value not in {"BUY", "SELL"}:
        raise ValueError(f"unsupported side: {side}")
    return value
