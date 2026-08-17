from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from kstock.domain.enums import Environment
from kstock.fixed_identity import OWNER_ACTOR_ID, fixed_account_ref

from .model import (
    AUTOMATION_RANK,
    KILL_SWITCH_RANK,
    AutomationLevel,
    AutomationProfile,
    ExecutionPermit,
    KillSwitchState,
    OddStatus,
    RuntimeControlState,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeControlError(ValueError):
    pass


class RuntimeControlStore:
    """현재 실행환경 하나의 권위 통제 상태.

    개인투자자용 구현이므로 다계좌 map이나 이중 통제 버전은 두지 않는다.
    실행 권한이 실제로 바뀔 때만 control_version을 증가시킨다.
    """

    def __init__(self, *, environment: Environment, initial_level: AutomationLevel) -> None:
        self._lock = RLock()
        self._state = RuntimeControlState(
            environment=environment,
            account_ref=fixed_account_ref(environment.value).value,
            control_version=0,
            kill_switch_state=KillSwitchState.NORMAL,
            automation_profile=AutomationProfile(
                current_level=initial_level,
                source="INITIAL",
                changed_at=utcnow(),
            ),
            odd_status=OddStatus.UNKNOWN,
        )

    def read(self) -> RuntimeControlState:
        with self._lock:
            return self._state

    def _replace_permission_state(self, **changes) -> RuntimeControlState:
        self._state = replace(
            self._state,
            control_version=self._state.control_version + 1,
            **changes,
        )
        return self._state

    def escalate_kill_switch(self, target: KillSwitchState, *, reason: str) -> RuntimeControlState:
        if not reason.strip():
            raise RuntimeControlError("reason is required")
        with self._lock:
            current = self._state.kill_switch_state
            if KILL_SWITCH_RANK[target] < KILL_SWITCH_RANK[current]:
                raise RuntimeControlError("kill switch escalation cannot relax state")
            if target is current:
                return self._state
            return self._replace_permission_state(kill_switch_state=target)

    def relax_kill_switch(
        self,
        target: KillSwitchState,
        *,
        actor_id: str,
        reason: str,
    ) -> RuntimeControlState:
        if actor_id != OWNER_ACTOR_ID:
            raise RuntimeControlError("only OWNER can relax kill switch")
        if not reason.strip():
            raise RuntimeControlError("reason is required")
        with self._lock:
            current = self._state.kill_switch_state
            if KILL_SWITCH_RANK[target] >= KILL_SWITCH_RANK[current]:
                raise RuntimeControlError("relaxation target must be less restrictive")
            return self._replace_permission_state(kill_switch_state=target)

    def promote_automation(
        self,
        target: AutomationLevel,
        *,
        actor_id: str,
        evidence_id: str,
        approval_id: str,
    ) -> RuntimeControlState:
        if actor_id != OWNER_ACTOR_ID:
            raise RuntimeControlError("only OWNER can promote automation")
        if not evidence_id or not approval_id:
            raise RuntimeControlError("promotion evidence and approval are required")
        with self._lock:
            current = self._state.automation_profile.current_level
            if AUTOMATION_RANK[target] <= AUTOMATION_RANK[current]:
                raise RuntimeControlError("promotion target must be higher")
            profile = AutomationProfile(
                current_level=target,
                source="PROMOTION",
                changed_at=utcnow(),
                evidence_id=evidence_id,
                approval_id=approval_id,
            )
            return self._replace_permission_state(automation_profile=profile)

    def demote_automation(self, target: AutomationLevel, *, source: str = "SYSTEM_GUARDIAN") -> RuntimeControlState:
        with self._lock:
            current = self._state.automation_profile.current_level
            if AUTOMATION_RANK[target] > AUTOMATION_RANK[current]:
                raise RuntimeControlError("demotion cannot increase automation")
            if target is current:
                return self._state
            profile = AutomationProfile(
                current_level=target,
                source=source,
                changed_at=utcnow(),
            )
            return self._replace_permission_state(automation_profile=profile)

    def set_odd_status(self, status: OddStatus, *, reason: str) -> RuntimeControlState:
        if not reason.strip():
            raise RuntimeControlError("reason is required")
        with self._lock:
            if status is self._state.odd_status:
                return self._state
            return self._replace_permission_state(odd_status=status)

    def note_quote_refresh(self) -> RuntimeControlState:
        """시세 갱신은 실행 권한 변경이 아니므로 control_version을 올리지 않는다."""
        return self.read()


def issue_execution_permit(*, permit_id: str, intent_id: str, policy_version: str, runtime: RuntimeControlState) -> ExecutionPermit:
    return ExecutionPermit(
        permit_id=permit_id,
        intent_id=intent_id,
        environment=runtime.environment,
        account_ref=runtime.account_ref,
        policy_version=policy_version,
        bound_control_version=runtime.control_version,
        issued_at=utcnow(),
    )


def validate_execution_permit(*, permit: ExecutionPermit, runtime: RuntimeControlState, active_policy_version: str) -> tuple[bool, str]:
    if permit.environment is not runtime.environment or permit.account_ref != runtime.account_ref:
        return False, "PERMIT_EXECUTION_WORLD_MISMATCH"
    if permit.policy_version != active_policy_version:
        return False, "POLICY_VERSION_CHANGED"
    if permit.bound_control_version != runtime.control_version:
        return False, "CONTROL_VERSION_CHANGED_RECHECK_REQUIRED"
    return True, "PASS"
