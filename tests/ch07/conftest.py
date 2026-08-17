from __future__ import annotations

from pathlib import Path

import pytest

from kstock.policy.loader import load_policy_bundle


@pytest.fixture
def ch7_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def paper_policy(ch7_root: Path):
    return load_policy_bundle(ch7_root / "config" / "policy" / "policy_bundle.paper.yaml")


@pytest.fixture
def live_policy(ch7_root: Path):
    return load_policy_bundle(ch7_root / "config" / "policy" / "policy_bundle.live.yaml")
