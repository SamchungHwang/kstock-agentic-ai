from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def configured_paper_environment(monkeypatch):
    """테스트에서는 실제 자격증명 대신 형식이 올바른 더미 값을 쓴다."""
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "test-paper-app-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "test-paper-app-secret")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT", "50012345-01")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT_PRODUCT", "01")
    monkeypatch.delenv("KIS_ALLOW_LIVE", raising=False)


@pytest.fixture
def project_root() -> Path:
    return ROOT
