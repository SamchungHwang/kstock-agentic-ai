from __future__ import annotations

import hashlib


def derive_submission_key(intent_id: str) -> str:
    if not intent_id:
        raise ValueError("intent_id is required")
    digest = hashlib.sha256(f"kstock:broker:{intent_id}".encode("utf-8")).hexdigest()
    return f"ks-{digest[:32]}"
