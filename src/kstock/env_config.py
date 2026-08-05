from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final


ENV_PAPER: Final[str] = "PAPER"
ENV_LIVE: Final[str] = "LIVE"
_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
_ACCOUNT_RE: Final[re.Pattern[str]] = re.compile(r"^\d{8}$")
_PRODUCT_RE: Final[re.Pattern[str]] = re.compile(r"^\d{2}$")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_dotenv_file(
    path: Path | None = None,
    *,
    override: bool = False,
) -> Path | None:
    """프로젝트 루트의 .env를 최소 규칙으로 읽는다.

    외부 의존성 없이 KEY=VALUE 형식만 지원한다. 주석·빈 줄·선행
    ``export``는 허용한다. 값의 따옴표는 제거하지만, 이 프로젝트의
    .env.example 지침대로 실제 값에는 따옴표를 쓰지 않는 것이 원칙이다.
    """
    target = path or project_root() / ".env"
    if not target.exists():
        return None

    text = target.read_text(encoding="utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
    return target


@dataclass(frozen=True)
class KisCredentials:
    environment: str
    app_key: str
    app_secret: str
    account_number: str
    account_product: str
    allow_live: bool
    source_file: str | None

    @property
    def account_display(self) -> str:
        if not self.account_number:
            return ""
        return f"{self.account_number}-{self.account_product}"

    @property
    def configured(self) -> bool:
        return not self.validation_errors()

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        if self.environment not in {ENV_PAPER, ENV_LIVE}:
            errors.append("ENVIRONMENT_INVALID")
        if not self.app_key:
            errors.append("APP_KEY_MISSING")
        if not self.app_secret:
            errors.append("APP_SECRET_MISSING")
        if not _ACCOUNT_RE.fullmatch(self.account_number):
            errors.append("ACCOUNT_NUMBER_INVALID")
        if not _PRODUCT_RE.fullmatch(self.account_product):
            errors.append("ACCOUNT_PRODUCT_INVALID")
        if self.environment == ENV_LIVE and not self.allow_live:
            errors.append("LIVE_NOT_ALLOWED")
        return errors

    def safe_summary(self) -> dict[str, object]:
        """비밀값을 노출하지 않는 진단용 요약."""
        return {
            "environment": self.environment,
            "app_key_configured": bool(self.app_key),
            "app_secret_configured": bool(self.app_secret),
            "account": mask_account(self.account_display),
            "account_product": self.account_product,
            "allow_live": self.allow_live,
            "source_file": self.source_file,
            "errors": self.validation_errors(),
        }


def _normalize_environment(value: str) -> str:
    return value.strip().upper()


def _parse_account(account_raw: str, product_raw: str) -> tuple[str, str]:
    account = account_raw.strip().replace(" ", "")
    product = product_raw.strip()

    if "-" in account:
        left, right = account.split("-", 1)
        account = left
        if right:
            product = right
    elif account.isdigit() and len(account) == 10:
        account, embedded_product = account[:8], account[8:]
        if not product:
            product = embedded_product

    return account, product


def resolve_kis_credentials(
    environment: str,
    *,
    dotenv_path: Path | None = None,
    load_dotenv: bool = True,
) -> KisCredentials:
    source: Path | None = None
    if load_dotenv:
        source = load_dotenv_file(dotenv_path, override=False)

    env = _normalize_environment(environment)
    if env == ENV_LIVE:
        prefix = "KIS_LIVE"
    else:
        prefix = "KIS_PAPER"

    account, product = _parse_account(
        os.environ.get(f"{prefix}_ACCOUNT", ""),
        os.environ.get(f"{prefix}_ACCOUNT_PRODUCT", ""),
    )
    allow_live = os.environ.get("KIS_ALLOW_LIVE", "").strip().lower() in _TRUE_VALUES

    return KisCredentials(
        environment=env,
        app_key=os.environ.get(f"{prefix}_APP_KEY", "").strip(),
        app_secret=os.environ.get(f"{prefix}_APP_SECRET", "").strip(),
        account_number=account,
        account_product=product,
        allow_live=allow_live,
        source_file=str(source) if source else None,
    )


def mask_account(value: str) -> str:
    if not value:
        return ""
    compact = value.replace("-", "")
    if len(compact) < 6:
        return "*" * len(compact)
    masked = compact[:2] + "*" * (len(compact) - 6) + compact[-4:]
    if len(compact) == 10:
        return f"{masked[:8]}-{masked[8:]}"
    return masked


def doctor_environment(environment: str) -> dict[str, object]:
    creds = resolve_kis_credentials(environment)
    errors = creds.validation_errors()
    return {
        "status": "PASS" if not errors else "FAIL",
        "credentials": creds.safe_summary(),
        "errors": errors,
    }
