from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kstock.domain.contracts import InvestmentThesis
from kstock.domain.enums import RiskDirection, ThesisStatus
from kstock.domain.thesis_lifecycle import ThesisLifecycleState


@dataclass(frozen=True, kw_only=True)
class OrderProposal:
    thesis_id: str
    security_id: str
    risk_direction: RiskDirection
    target_weight: Decimal


@dataclass(frozen=True, kw_only=True)
class ProposalBuildResult:
    status: str
    code: str
    proposal: OrderProposal | None


def build_proposal(
    *,
    thesis: InvestmentThesis,
    lifecycle: ThesisLifecycleState,
    risk_direction: RiskDirection,
    target_weight: Decimal,
) -> ProposalBuildResult:
    if not isinstance(thesis, InvestmentThesis):
        raise TypeError("thesis must be an issued InvestmentThesis")
    if lifecycle.thesis_id != thesis.contract_id:
        return ProposalBuildResult(status="BLOCKED", code="THESIS_LIFECYCLE_MISMATCH", proposal=None)

    if lifecycle.status is not ThesisStatus.ACTIVE and risk_direction is RiskDirection.INCREASE:
        return ProposalBuildResult(status="BLOCKED", code="THESIS_NOT_ACTIVE", proposal=None)

    if target_weight < 0:
        return ProposalBuildResult(status="BLOCKED", code="INVALID_TARGET_WEIGHT", proposal=None)

    proposal = OrderProposal(
        thesis_id=thesis.contract_id,
        security_id=thesis.security_id,
        risk_direction=risk_direction,
        target_weight=target_weight,
    )
    return ProposalBuildResult(status="PASS", code="PASS", proposal=proposal)
