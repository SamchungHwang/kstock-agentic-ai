from __future__ import annotations

from collections.abc import Mapping

from kstock.domain.enums import RecoveryClass


def recovery_class_for(code: str, mapping: Mapping[str, RecoveryClass | str]) -> RecoveryClass:
    raw = mapping.get(code)
    if raw is None:
        return RecoveryClass.HUMAN_REQUIRED
    if isinstance(raw, RecoveryClass):
        return raw
    try:
        return RecoveryClass(str(raw))
    except ValueError:
        return RecoveryClass.HUMAN_REQUIRED
