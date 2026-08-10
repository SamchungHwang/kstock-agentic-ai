from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from kstock.domain.contracts import InvestmentThesis
from kstock.domain.enums import ThesisStatus
from kstock.domain.thesis_lifecycle import ThesisLifecycleState


@dataclass(frozen=True, kw_only=True)
class PortfolioSnapshot:
    nav: Decimal
    cash: Decimal
    current_exposure: Decimal


@dataclass(frozen=True, kw_only=True)
class SizingResult:
    target_weight: Decimal
    decision_hash: str


def _as_decimal(value: object, default: str) -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def size_position(
    *,
    thesis: InvestmentThesis,
    lifecycle: ThesisLifecycleState,
    snapshot: PortfolioSnapshot,
    policy: Mapping[str, object],
) -> SizingResult:
    if not isinstance(thesis, InvestmentThesis):
        raise TypeError("thesis must be an issued InvestmentThesis")
    if lifecycle.thesis_id != thesis.contract_id:
        raise ValueError("lifecycle does not belong to InvestmentThesis")
    if lifecycle.status is not ThesisStatus.ACTIVE:
        raise ValueError("InvestmentThesis must be ACTIVE for sizing")

    max_weight = _as_decimal(policy.get("max_position_weight"), "0")
    multiplier = _as_decimal(policy.get("conviction_multiplier"), "1")
    min_cash_buffer = _as_decimal(policy.get("min_cash_buffer"), "0")

    cash_ratio = Decimal("0") if snapshot.nav == 0 else snapshot.cash / snapshot.nav
    deployable_by_cash = max(Decimal("0"), cash_ratio - min_cash_buffer)
    conviction_weight = thesis.conviction * multiplier
    target_weight = max(Decimal("0"), min(max_weight, conviction_weight, deployable_by_cash))

    payload = {
        "thesis_hash": thesis.contract_hash,
        "thesis_status": lifecycle.status.value,
        "snapshot": {
            "nav": format(snapshot.nav, "f"),
            "cash": format(snapshot.cash, "f"),
            "current_exposure": format(snapshot.current_exposure, "f"),
        },
        "policy": {str(k): str(v) for k, v in sorted(policy.items(), key=lambda item: str(item[0]))},
        "target_weight": format(target_weight, "f"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    decision_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return SizingResult(target_weight=target_weight, decision_hash=decision_hash)
