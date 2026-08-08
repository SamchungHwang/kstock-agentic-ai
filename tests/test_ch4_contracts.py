from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kstock.v2v3_contracts import (
    CapabilityError,
    ConsoleVersion,
    ContractError,
    Decision,
    GuardState,
    InvestmentThesisDraft,
    PromotionEvidence,
    ResponseKind,
    SubmissionRegistry,
)
from kstock.v2v3_flow import (
    create_proposal,
    decide_proposal,
    emergency_action_allowed,
    issue_intent,
    judge_run,
    request_revision,
    size_portfolio,
    submit_approved_intent,
    validate_submit_argv,
    validate_thesis,
)


NOW = datetime(2026, 8, 8, 1, 0, tzinfo=timezone.utc)


def evidence(**overrides):
    values = dict(
        v1_safe_operations_passed=True,
        reconciliation_clean=True,
        audit_healthy=True,
        kill_switch_off=True,
        no_unknown_orders=True,
        v2_contract_tests_passed=True,
        paper_environment=True,
    )
    values.update(overrides)
    return PromotionEvidence(**values)


def thesis():
    return validate_thesis(
        version=ConsoleVersion.V2,
        draft=InvestmentThesisDraft(
            draft_id="draft_1",
            payload={"symbol": "005930", "summary": "test thesis"},
        ),
    )


def sizing(t=None, **input_overrides):
    inputs = dict(
        symbol="005930",
        price=80000,
        capital_krw=50_000_000,
        max_weight=0.08,
        liquidity_qty_cap=100,
    )
    inputs.update(input_overrides)
    return size_portfolio(
        version=ConsoleVersion.V2,
        thesis=t or thesis(),
        account_snapshot_id="acct_1",
        policy_version="p1",
        inputs=inputs,
    )


def approved_proposal():
    t = thesis()
    s = sizing(t)
    p = create_proposal(version=ConsoleVersion.V2, thesis=t, sizing=s, now=NOW)
    d = decide_proposal(
        version=ConsoleVersion.V2,
        proposal=p,
        decision=Decision.APPROVE,
        card_hash=p.proposal_hash,
        reason="approved",
        now=NOW,
    )
    return t, s, p, d


# 1. V2 Judge 성공은 주문/Intent를 생성하지 않는다.
def test_01_v2_judge_does_not_create_order_or_intent():
    result = judge_run(
        version=ConsoleVersion.V2,
        evidence_packet_id="ep_1",
        strategy_id="st_1",
    )
    assert result.draft_id
    assert not hasattr(result, "intent_id")
    assert not hasattr(result, "broker_order_id")


# 2. 비정상 ModelResponse는 빈 Thesis로 통과하지 않는다.
@pytest.mark.parametrize("kind", [ResponseKind.REFUSAL, ResponseKind.INCOMPLETE, ResponseKind.API_ERROR])
def test_02_non_ok_response_cannot_cross_boundary(kind):
    with pytest.raises(ContractError):
        validate_thesis(
            version=ConsoleVersion.V2,
            draft=InvestmentThesisDraft("d", {}, response_kind=kind),
        )


# 3. Draft를 사이징에 직접 사용할 수 없다.
def test_03_draft_cannot_be_sized():
    with pytest.raises(ContractError):
        size_portfolio(
            version=ConsoleVersion.V2,
            thesis=InvestmentThesisDraft("d", {"symbol": "005930"}),  # type: ignore[arg-type]
            account_snapshot_id="a",
            policy_version="p1",
            inputs={"symbol": "005930", "price": 1, "capital_krw": 10, "max_weight": 0.1, "liquidity_qty_cap": 1},
        )


# 4. 같은 입력은 같은 결과 해시를 만든다.
def test_04_sizing_is_deterministic_by_hash():
    t = thesis()
    a = sizing(t)
    b = sizing(t)
    assert a.result_hash == b.result_hash


# 5. 산식 입력과 제한 요인이 모두 노출된다.
def test_05_sizing_exposes_formula_inputs_and_limiting_factor():
    s = sizing()
    assert s.formula
    assert s.inputs["capital_krw"] == 50_000_000
    assert s.limiting_factor in {"MAX_WEIGHT", "LIQUIDITY"}


# 6. 카드 원문이 바뀌면 기존 승인 시도가 거부된다.
def test_06_changed_proposal_card_rejected():
    t, s, p, _ = approved_proposal()
    with pytest.raises(ContractError):
        decide_proposal(
            version=ConsoleVersion.V2,
            proposal=p,
            decision=Decision.APPROVE,
            card_hash="tampered",
            reason="",
        )


# 7. 승인 hash 불일치 시 Intent 발급 거부.
def test_07_approval_hash_must_match_proposal():
    _, _, p, d = approved_proposal()
    bad = replace(d, proposal_hash="bad")
    with pytest.raises(ContractError):
        issue_intent(
            version=ConsoleVersion.V3_PAPER,
            proposal=p,
            approval=bad,
            environment="PAPER",
            now=NOW,
        )


# 8. 거절/수정은 원문을 덮어쓰지 않고 이벤트로 남는다.
def test_08_reject_revision_are_append_only_events():
    _, _, p, _ = approved_proposal()
    before = p.proposal_hash
    reject = decide_proposal(version=ConsoleVersion.V2, proposal=p, decision=Decision.REJECT, card_hash=p.proposal_hash, reason="no")
    revision = decide_proposal(version=ConsoleVersion.V2, proposal=p, decision=Decision.REQUEST_REVISION, card_hash=p.proposal_hash, reason="re-size")
    assert reject.event_id != revision.event_id
    assert p.proposal_hash == before


# 9. 수량 직접 편집 필드가 화면/CLI에 없다.
def test_09_no_qty_editor_or_raw_order_args(project_root):
    screen = json.loads((project_root / "contracts" / "console_v2_v3_screen.json").read_text(encoding="utf-8"))
    cli = json.loads((project_root / "contracts" / "cli_io_contracts.json").read_text(encoding="utf-8"))
    assert screen["v3_submit_panel"]["editable_fields"] == []
    assert screen["v3_submit_panel"]["raw_order_form"] is False
    assert "qty" in cli["commands"]["order submit-approved"]["forbidden_args"]


# 10. 수정 요청 후 새 SizingResult/Proposal 생성.
def test_10_revision_creates_new_sizing_and_proposal():
    t, s, p, _ = approved_proposal()
    event = decide_proposal(version=ConsoleVersion.V2, proposal=p, decision=Decision.REQUEST_REVISION, card_hash=p.proposal_hash, reason="lower risk")
    new_s, new_p = request_revision(
        version=ConsoleVersion.V2,
        old_proposal=p,
        old_decision=event,
        thesis=t,
        account_snapshot_id="acct_2",
        policy_version="p1",
        revised_inputs={**s.inputs, "max_weight": 0.04},
    )
    assert new_s.sizing_id != s.sizing_id
    assert new_p.proposal_id != p.proposal_id
    assert new_p.proposal_hash != p.proposal_hash


# 11. V2에서는 intent issue/broker submit capability가 없다.
def test_11_v2_cannot_issue_intent_or_submit():
    _, _, p, d = approved_proposal()
    with pytest.raises(CapabilityError):
        issue_intent(version=ConsoleVersion.V2, proposal=p, approval=d, environment="PAPER", now=NOW)


# 12. V3 submit CLI는 raw symbol/qty/price를 거부.
@pytest.mark.parametrize("arg", ["--symbol", "--qty", "--price"])
def test_12_submit_argv_rejects_raw_fields(arg):
    with pytest.raises(ContractError):
        validate_submit_argv(["order", "submit-approved", "--intent-id", "i1", arg, "x"])


# 13. 승인되지 않은 proposal로 Intent를 발급할 수 없다.
def test_13_unapproved_proposal_cannot_issue_intent():
    _, _, p, _ = approved_proposal()
    rejected = decide_proposal(version=ConsoleVersion.V2, proposal=p, decision=Decision.REJECT, card_hash=p.proposal_hash, reason="reject")
    with pytest.raises(ContractError):
        issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=rejected, environment="PAPER", now=NOW)


# 14. 만료 Intent는 제출 직전 차단.
def test_14_expired_intent_blocked():
    _, _, p, d = approved_proposal()
    intent = issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=d, environment="PAPER", ttl_seconds=1, now=NOW)
    result = submit_approved_intent(
        version=ConsoleVersion.V3_PAPER,
        intent=intent,
        environment="PAPER",
        guard_state=GuardState.PASS,
        evidence=evidence(),
        registry=SubmissionRegistry(),
        now=NOW + timedelta(seconds=2),
    )
    assert result.code == "INTENT_EXPIRED"


# 15. PAPER Intent를 LIVE에 제출할 수 없다.
def test_15_paper_intent_cannot_submit_to_live():
    _, _, p, d = approved_proposal()
    intent = issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=d, environment="PAPER", now=NOW)
    result = submit_approved_intent(
        version=ConsoleVersion.V3_PAPER,
        intent=intent,
        environment="LIVE",
        guard_state=GuardState.PASS,
        evidence=evidence(),
        registry=SubmissionRegistry(),
        now=NOW,
    )
    assert result.status.value == "BLOCKED"


# 16. 동일 Intent 중복 제출 거부.
def test_16_duplicate_intent_submit_blocked():
    _, _, p, d = approved_proposal()
    intent = issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=d, environment="PAPER", now=NOW)
    registry = SubmissionRegistry()
    first = submit_approved_intent(version=ConsoleVersion.V3_PAPER, intent=intent, environment="PAPER", guard_state=GuardState.PASS, evidence=evidence(), registry=registry, now=NOW)
    second = submit_approved_intent(version=ConsoleVersion.V3_PAPER, intent=intent, environment="PAPER", guard_state=GuardState.PASS, evidence=evidence(), registry=registry, now=NOW)
    assert first.status.value == "SUCCESS"
    assert second.code == "INTENT_ALREADY_SUBMITTED"


# 17. timeout -> UNKNOWN, automatic retry=false.
def test_17_timeout_is_unknown_without_automatic_retry():
    _, _, p, d = approved_proposal()
    intent = issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=d, environment="PAPER", now=NOW)
    result = submit_approved_intent(version=ConsoleVersion.V3_PAPER, intent=intent, environment="PAPER", guard_state=GuardState.PASS, evidence=evidence(), registry=SubmissionRegistry(), now=NOW, simulate_timeout=True)
    assert result.status.value == "UNKNOWN"
    assert result.automatic_retry is False


# 18. 대사/감사/킬스위치 이상이면 submit capability 차단.
@pytest.mark.parametrize("bad_evidence", [
    {"reconciliation_clean": False},
    {"audit_healthy": False},
    {"kill_switch_off": False},
])
def test_18_submit_blocked_by_safety_evidence(bad_evidence):
    _, _, p, d = approved_proposal()
    intent = issue_intent(version=ConsoleVersion.V3_PAPER, proposal=p, approval=d, environment="PAPER", now=NOW)
    result = submit_approved_intent(version=ConsoleVersion.V3_PAPER, intent=intent, environment="PAPER", guard_state=GuardState.PASS, evidence=evidence(**bad_evidence), registry=SubmissionRegistry(), now=NOW)
    assert result.code == "CAPABILITY_DISABLED"


# 19. 제출 중에도 halt/cancel 버튼은 항상 허용.
def test_19_emergency_buttons_are_always_available():
    assert emergency_action_allowed("halt_trading", broker_submit_in_progress=True)
    assert emergency_action_allowed("cancel_open_order", broker_submit_in_progress=True)


# 20. 승격 증거가 사라지면 broker_submit capability 자동 비활성화.
def test_20_capability_drops_when_evidence_disappears():
    ok = evidence()
    assert ok.broker_submit_enabled()
    degraded = evidence(audit_healthy=False)
    assert not degraded.broker_submit_enabled()
