from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .v2v3_contracts import (
    BrokerOrderResult,
    CapabilityError,
    ConsoleVersion,
    ContractError,
    Decision,
    GuardState,
    InvestmentThesis,
    InvestmentThesisDraft,
    JudgeRunResult,
    OrderIntent,
    OrderProposal,
    PromotionEvidence,
    ProposalDecision,
    ResponseKind,
    SizingResult,
    SubmissionRegistry,
    SubmitStatus,
    canonical_hash,
    require_version,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def judge_run(
    *,
    version: ConsoleVersion,
    evidence_packet_id: str,
    strategy_id: str,
    response_kind: ResponseKind = ResponseKind.OK,
) -> JudgeRunResult:
    require_version(version, ConsoleVersion.V2)
    draft_id = _id("draft") if response_kind is ResponseKind.OK else None
    return JudgeRunResult(
        evidence_packet_id=evidence_packet_id,
        strategy_id=strategy_id,
        response_kind=response_kind,
        draft_id=draft_id,
        message="Judge draft created" if draft_id else "Judge response not usable",
    )


def validate_thesis(
    *,
    version: ConsoleVersion,
    draft: InvestmentThesisDraft,
) -> InvestmentThesis:
    require_version(version, ConsoleVersion.V2)
    if draft.response_kind is not ResponseKind.OK:
        raise ContractError(f"response kind cannot cross boundary: {draft.response_kind.value}")
    if not draft.payload:
        raise ContractError("empty thesis draft")
    thesis_payload = dict(draft.payload)
    thesis_hash = canonical_hash(thesis_payload)
    return InvestmentThesis(
        thesis_id=_id("thesis"),
        draft_id=draft.draft_id,
        payload=thesis_payload,
        thesis_hash=thesis_hash,
    )


def size_portfolio(
    *,
    version: ConsoleVersion,
    thesis: InvestmentThesis,
    account_snapshot_id: str,
    policy_version: str,
    inputs: dict[str, Any],
) -> SizingResult:
    require_version(version, ConsoleVersion.V2)
    if not isinstance(thesis, InvestmentThesis):
        raise ContractError("InvestmentThesisDraft cannot be used for sizing")
    required = ("symbol", "price", "capital_krw", "max_weight", "liquidity_qty_cap")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ContractError(f"missing sizing inputs: {missing}")
    price = int(inputs["price"])
    capital = int(inputs["capital_krw"])
    max_weight = float(inputs["max_weight"])
    liquidity_qty_cap = int(inputs["liquidity_qty_cap"])
    if price <= 0:
        raise ContractError("price must be positive")
    weight_qty_cap = int((capital * max_weight) // price)
    qty = max(0, min(weight_qty_cap, liquidity_qty_cap))
    limiting_factor = "MAX_WEIGHT" if weight_qty_cap <= liquidity_qty_cap else "LIQUIDITY"
    formula = "qty=min(floor(capital_krw*max_weight/price), liquidity_qty_cap)"
    hash_payload = {
        "thesis_hash": thesis.thesis_hash,
        "account_snapshot_id": account_snapshot_id,
        "policy_version": policy_version,
        "inputs": inputs,
        "formula": formula,
        "limiting_factor": limiting_factor,
        "qty": qty,
        "limit_price": price,
    }
    return SizingResult(
        sizing_id=_id("sizing"),
        thesis_id=thesis.thesis_id,
        account_snapshot_id=account_snapshot_id,
        policy_version=policy_version,
        inputs=dict(inputs),
        formula=formula,
        limiting_factor=limiting_factor,
        qty=qty,
        limit_price=price,
        result_hash=canonical_hash(hash_payload),
    )


def create_proposal(
    *,
    version: ConsoleVersion,
    thesis: InvestmentThesis,
    sizing: SizingResult,
    now: datetime | None = None,
) -> OrderProposal:
    require_version(version, ConsoleVersion.V2)
    symbol = str(sizing.inputs["symbol"])
    created_at = now or utcnow()
    payload = {
        "thesis_id": thesis.thesis_id,
        "sizing_id": sizing.sizing_id,
        "sizing_hash": sizing.result_hash,
        "symbol": symbol,
        "qty": sizing.qty,
        "limit_price": sizing.limit_price,
    }
    return OrderProposal(
        proposal_id=_id("proposal"),
        thesis_id=thesis.thesis_id,
        sizing_id=sizing.sizing_id,
        symbol=symbol,
        qty=sizing.qty,
        limit_price=sizing.limit_price,
        proposal_hash=canonical_hash(payload),
        created_at=created_at,
    )


def decide_proposal(
    *,
    version: ConsoleVersion,
    proposal: OrderProposal,
    decision: Decision,
    card_hash: str,
    reason: str,
    now: datetime | None = None,
) -> ProposalDecision:
    require_version(version, ConsoleVersion.V2)
    if card_hash != proposal.proposal_hash:
        raise ContractError("proposal card changed after it was opened")
    if decision in {Decision.REJECT, Decision.REQUEST_REVISION} and not reason.strip():
        raise ContractError("reason is required")
    return ProposalDecision(
        event_id=_id("proposal_decision"),
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        decision=decision,
        reason=reason,
        decided_at=now or utcnow(),
    )


def request_revision(
    *,
    version: ConsoleVersion,
    old_proposal: OrderProposal,
    old_decision: ProposalDecision,
    thesis: InvestmentThesis,
    account_snapshot_id: str,
    policy_version: str,
    revised_inputs: dict[str, Any],
) -> tuple[SizingResult, OrderProposal]:
    require_version(version, ConsoleVersion.V2)
    if old_decision.decision is not Decision.REQUEST_REVISION:
        raise ContractError("revision event required")
    new_sizing = size_portfolio(
        version=version,
        thesis=thesis,
        account_snapshot_id=account_snapshot_id,
        policy_version=policy_version,
        inputs=revised_inputs,
    )
    new_proposal = create_proposal(version=version, thesis=thesis, sizing=new_sizing)
    if new_proposal.proposal_id == old_proposal.proposal_id:
        raise AssertionError("proposal must be append-only")
    return new_sizing, new_proposal


def issue_intent(
    *,
    version: ConsoleVersion,
    proposal: OrderProposal,
    approval: ProposalDecision,
    environment: str,
    ttl_seconds: int = 300,
    now: datetime | None = None,
) -> OrderIntent:
    require_version(version, ConsoleVersion.V3_PAPER)
    if approval.decision is not Decision.APPROVE:
        raise ContractError("approved proposal required")
    if approval.proposal_id != proposal.proposal_id:
        raise ContractError("approval does not belong to proposal")
    if approval.proposal_hash != proposal.proposal_hash:
        raise ContractError("proposal hash mismatch")
    issued_at = now or utcnow()
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload = {
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "environment": environment,
        "symbol": proposal.symbol,
        "qty": proposal.qty,
        "limit_price": proposal.limit_price,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    return OrderIntent(
        intent_id=_id("intent"),
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash,
        environment=environment,
        symbol=proposal.symbol,
        qty=proposal.qty,
        limit_price=proposal.limit_price,
        issued_at=issued_at,
        expires_at=expires_at,
        intent_hash=canonical_hash(payload),
    )


def validate_submit_argv(argv: list[str]) -> None:
    forbidden = {"--symbol", "--qty", "--price"}
    present = sorted(forbidden.intersection(argv))
    if present:
        raise ContractError(f"raw order args forbidden: {present}")
    if "--intent-id" not in argv:
        raise ContractError("--intent-id is required")


def submit_approved_intent(
    *,
    version: ConsoleVersion,
    intent: OrderIntent,
    environment: str,
    guard_state: GuardState,
    evidence: PromotionEvidence,
    registry: SubmissionRegistry,
    now: datetime | None = None,
    simulate_timeout: bool = False,
) -> BrokerOrderResult:
    require_version(version, ConsoleVersion.V3_PAPER)
    current = now or utcnow()
    if not evidence.broker_submit_enabled():
        return BrokerOrderResult(SubmitStatus.BLOCKED, "CAPABILITY_DISABLED", intent.intent_id)
    if environment != "PAPER":
        return BrokerOrderResult(SubmitStatus.BLOCKED, "V3_PAPER_ONLY", intent.intent_id)
    if intent.environment != environment:
        return BrokerOrderResult(SubmitStatus.BLOCKED, "INTENT_ENVIRONMENT_MISMATCH", intent.intent_id)
    if current >= intent.expires_at:
        return BrokerOrderResult(SubmitStatus.BLOCKED, "INTENT_EXPIRED", intent.intent_id)
    if guard_state is not GuardState.PASS:
        code = "PREFLIGHT_UNKNOWN" if guard_state is GuardState.UNKNOWN else "PREFLIGHT_BLOCKED"
        return BrokerOrderResult(SubmitStatus.BLOCKED, code, intent.intent_id)
    if registry.was_submitted(intent.intent_id):
        return BrokerOrderResult(SubmitStatus.BLOCKED, "INTENT_ALREADY_SUBMITTED", intent.intent_id)
    if simulate_timeout:
        return BrokerOrderResult(
            SubmitStatus.UNKNOWN,
            "BROKER_SUBMIT_UNKNOWN",
            intent.intent_id,
            broker_order_id=None,
            automatic_retry=False,
        )
    registry.mark_submitted(intent.intent_id)
    return BrokerOrderResult(
        SubmitStatus.SUCCESS,
        "BROKER_ORDER_ACCEPTED",
        intent.intent_id,
        broker_order_id=_id("broker"),
        automatic_retry=False,
    )


def emergency_action_allowed(action: str, *, broker_submit_in_progress: bool) -> bool:
    return action in {"halt_trading", "cancel_open_order"}
