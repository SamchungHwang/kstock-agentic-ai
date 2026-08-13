from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


OWNER_ACTOR_ID = "OWNER"


class FixedAccountRef(str, Enum):
    PAPER_PRIMARY = "PAPER_PRIMARY"
    LIVE_PRIMARY = "LIVE_PRIMARY"


_FIXED_ACCOUNT_BY_ENV = {
    "PAPER": FixedAccountRef.PAPER_PRIMARY,
    "LIVE": FixedAccountRef.LIVE_PRIMARY,
}


def normalize_environment(value: str) -> str:
    env = value.strip().upper()
    if env not in _FIXED_ACCOUNT_BY_ENV:
        raise ValueError(f"unsupported environment: {value!r}")
    return env


def fixed_account_ref(environment: str) -> FixedAccountRef:
    return _FIXED_ACCOUNT_BY_ENV[normalize_environment(environment)]


def assert_fixed_account_binding(environment: str, account_ref: str | FixedAccountRef) -> None:
    expected = fixed_account_ref(environment).value
    actual = account_ref.value if isinstance(account_ref, FixedAccountRef) else str(account_ref)
    if actual != expected:
        raise ValueError(
            f"fixed account binding mismatch: environment={normalize_environment(environment)}, "
            f"expected={expected}, actual={actual}"
        )


@dataclass(frozen=True, slots=True)
class OperatingIdentity:
    """개인투자자 1명 + 환경별 고정계좌 1개의 실행 정체성."""

    environment: str
    account_ref: FixedAccountRef
    owner_actor_id: str = OWNER_ACTOR_ID

    @classmethod
    def for_environment(cls, environment: str) -> "OperatingIdentity":
        env = normalize_environment(environment)
        return cls(environment=env, account_ref=fixed_account_ref(env))
