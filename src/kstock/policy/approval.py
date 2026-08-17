from __future__ import annotations

from kstock.fixed_identity import OWNER_ACTOR_ID

from .model import ApprovalRiskBinding, PolicyBundle, RiskDirectionAssessment


def validate_approval_context(
    *,
    approval: ApprovalRiskBinding | None,
    proposal_hash: str,
    current_assessment: RiskDirectionAssessment,
    bundle: PolicyBundle,
) -> tuple[bool, str]:
    if approval is None:
        return False, "OWNER_APPROVAL_REQUIRED"
    if approval.approved_by != OWNER_ACTOR_ID:
        return False, "APPROVAL_NOT_BY_OWNER"
    if approval.proposal_hash != proposal_hash:
        return False, "APPROVAL_PROPOSAL_CHANGED"
    if approval.environment is not bundle.environment or approval.account_ref != bundle.account_ref:
        return False, "APPROVAL_EXECUTION_WORLD_MISMATCH"
    if approval.approved_direction is not current_assessment.direction:
        return False, "APPROVAL_RISK_DIRECTION_CHANGED"
    # assessment hash는 감사·재현용으로 보존한다. 재승인 기준은 이 단순화 버전에서는
    # proposal과 RiskDirection의 의미 변화다. 단순 재조회 시각 변화만으로 재승인하지 않는다.
    return True, "PASS"
