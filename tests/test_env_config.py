from __future__ import annotations

from pathlib import Path

from kstock.env_config import (
    doctor_environment,
    load_dotenv_file,
    resolve_kis_credentials,
)


def test_paper_account_can_include_product_code(monkeypatch):
    monkeypatch.setenv("KIS_PAPER_ACCOUNT", "50012345-01")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT_PRODUCT", "99")
    creds = resolve_kis_credentials("PAPER", load_dotenv=False)
    assert creds.account_number == "50012345"
    assert creds.account_product == "01"
    assert creds.account_display == "50012345-01"


def test_live_requires_explicit_allow_flag(monkeypatch):
    monkeypatch.setenv("KIS_LIVE_APP_KEY", "live-key")
    monkeypatch.setenv("KIS_LIVE_APP_SECRET", "live-secret")
    monkeypatch.setenv("KIS_LIVE_ACCOUNT", "12345678")
    monkeypatch.setenv("KIS_LIVE_ACCOUNT_PRODUCT", "01")
    monkeypatch.delenv("KIS_ALLOW_LIVE", raising=False)

    blocked = resolve_kis_credentials("LIVE", load_dotenv=False)
    assert "LIVE_NOT_ALLOWED" in blocked.validation_errors()

    monkeypatch.setenv("KIS_ALLOW_LIVE", "1")
    allowed = resolve_kis_credentials("LIVE", load_dotenv=False)
    assert allowed.validation_errors() == []


def test_dotenv_does_not_override_os_environment(tmp_path: Path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "KIS_PAPER_APP_KEY=file-key\n"
        "KIS_PAPER_APP_SECRET=file-secret\n"
        "KIS_PAPER_ACCOUNT=50012345-01\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "os-key")
    load_dotenv_file(dotenv, override=False)
    assert resolve_kis_credentials(
        "PAPER", load_dotenv=False
    ).app_key == "os-key"


def test_doctor_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "very-sensitive-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "very-sensitive-secret")
    result = doctor_environment("PAPER")
    text = repr(result)
    assert "very-sensitive-key" not in text
    assert "very-sensitive-secret" not in text
    assert result["credentials"]["app_key_configured"] is True
    assert result["credentials"]["app_secret_configured"] is True


def test_paper_and_live_use_distinct_fixed_logical_accounts(monkeypatch):
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "paper-key")
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "paper-secret")
    monkeypatch.setenv("KIS_PAPER_ACCOUNT", "50012345-01")
    monkeypatch.setenv("KIS_LIVE_APP_KEY", "live-key")
    monkeypatch.setenv("KIS_LIVE_APP_SECRET", "live-secret")
    monkeypatch.setenv("KIS_LIVE_ACCOUNT", "12345678-01")
    monkeypatch.setenv("KIS_ALLOW_LIVE", "1")

    paper = resolve_kis_credentials("PAPER", load_dotenv=False)
    live = resolve_kis_credentials("LIVE", load_dotenv=False)

    assert paper.account_ref == "PAPER_PRIMARY"
    assert live.account_ref == "LIVE_PRIMARY"
    assert paper.account_ref != live.account_ref
    assert paper.account_display != live.account_display
