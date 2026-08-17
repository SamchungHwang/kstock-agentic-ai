from __future__ import annotations

from kstock.policy.model import KillSwitchState
from kstock.policy.runtime_control import RuntimeControlStore


class SafetyKernelForbidden(RuntimeError):
    pass


class SafetyKernel:
    """PolicyBundle과 독립된 최소 정지 경로. 강화만 가능하다."""

    def __init__(self, store: RuntimeControlStore) -> None:
        self._store = store

    def escalate(self, target: KillSwitchState, *, reason: str):
        if target is KillSwitchState.NORMAL:
            raise SafetyKernelForbidden("Safety Kernel cannot relax to NORMAL")
        return self._store.escalate_kill_switch(target, reason=reason)

    def deactivate(self, *args, **kwargs):
        raise SafetyKernelForbidden("Safety Kernel cannot deactivate kill switch")

    def attempt_submission(self, *args, **kwargs):
        raise SafetyKernelForbidden("Safety Kernel cannot submit orders")

    def attempt_cancel(self, *args, **kwargs):
        raise SafetyKernelForbidden("Safety Kernel cannot cancel orders")

    def promote_automation(self, *args, **kwargs):
        raise SafetyKernelForbidden("Safety Kernel cannot promote automation")
