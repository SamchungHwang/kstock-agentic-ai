from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from kstock.env_config import resolve_kis_credentials, resolve_kis_hts_user_id
from kstock.fixed_identity import normalize_environment
from kstock.state_store import data_dir


PROD_BASE_URL = "https://openapi.koreainvestment.com:9443"
PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
TOKEN_PATH = "/oauth2/tokenP"


class KisReadOnlyError(RuntimeError):
    """KIS 조회 경계에서 발생한 명시적인 실패."""


@dataclass(frozen=True, slots=True)
class KisReadOnlyConfig:
    environment: str
    app_key: str
    app_secret: str
    hts_user_id: str
    base_url: str

    @classmethod
    def from_environment(cls, environment: str) -> "KisReadOnlyConfig":
        env = normalize_environment(environment)
        creds = resolve_kis_credentials(env)
        errors = [e for e in creds.validation_errors() if e != "LIVE_NOT_ALLOWED"]
        if errors:
            raise KisReadOnlyError("KIS_READONLY_CONFIG_INVALID:" + ",".join(errors))

        hts_user_id = resolve_kis_hts_user_id(load_dotenv=False)
        if not hts_user_id:
            raise KisReadOnlyError("KIS_HTS_USER_ID_MISSING")

        return cls(
            environment=env,
            app_key=creds.app_key,
            app_secret=creds.app_secret,
            hts_user_id=hts_user_id,
            base_url=PROD_BASE_URL if env == "LIVE" else PAPER_BASE_URL,
        )


@dataclass(frozen=True, slots=True)
class CachedToken:
    access_token: str
    expires_at_monotonic: float


class KisReadOnlyHttpClient:
    """주문 기능이 전혀 없는 KIS REST 조회 전용 클라이언트.

    관심종목 조회를 위해 접근토큰과 일반 GET API만 제공한다. Broker 주문
    Adapter와 의도적으로 분리해, 관심종목 동기화가 주문 경로를 만들지 않게 한다.
    """

    def __init__(self, config: KisReadOnlyConfig, *, timeout_seconds: float = 10.0) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self._token: CachedToken | None = None

    def _token_cache_path(self) -> Path:
        return data_dir() / "kis_readonly_token.json"

    def _load_cached_token(self) -> str | None:
        if self._token and self._token.expires_at_monotonic > time.monotonic() + 60:
            return self._token.access_token

        path = self._token_cache_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            expires_at_epoch = float(raw.get("expires_at_epoch", 0))
            access_token = str(raw.get("access_token", ""))
            if access_token and expires_at_epoch > time.time() + 60:
                remaining = expires_at_epoch - time.time()
                self._token = CachedToken(access_token, time.monotonic() + remaining)
                return access_token
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        return None

    def _save_token(self, token: str, expires_in: int) -> None:
        # 토큰은 환경별 data 디렉터리에만 저장하고 감사 로그/콘솔에는 노출하지 않는다.
        path = self._token_cache_path()
        expires_in = max(60, int(expires_in))
        payload = {
            "access_token": token,
            "expires_at_epoch": time.time() + expires_in,
        }
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(path)
        self._token = CachedToken(token, time.monotonic() + expires_in)

    def access_token(self) -> str:
        cached = self._load_cached_token()
        if cached:
            return cached

        body = json.dumps({
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.config.base_url + TOKEN_PATH,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        payload = self._open_json(request)
        token = str(payload.get("access_token", ""))
        if not token:
            raise KisReadOnlyError(
                f"KIS_TOKEN_MISSING:{payload.get('error_code') or payload.get('msg1') or 'UNKNOWN'}"
            )
        expires_in = int(payload.get("expires_in", 86400) or 86400)
        self._save_token(token, expires_in)
        return token

    def get(self, *, path: str, tr_id: str, params: Mapping[str, str]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{self.config.base_url}{path}?{query}",
            method="GET",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "authorization": f"Bearer {self.access_token()}",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "tr_cont": "",
            },
        )
        payload = self._open_json(request)
        if str(payload.get("rt_cd", "0")) != "0":
            code = payload.get("msg_cd") or payload.get("rt_cd") or "UNKNOWN"
            message = payload.get("msg1") or "KIS API error"
            raise KisReadOnlyError(f"KIS_API_ERROR:{code}:{message}")
        return payload

    def _open_json(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = response.read().decode("utf-8")
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    raise KisReadOnlyError("KIS_RESPONSE_NOT_OBJECT")
                return payload
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                detail = ""
            raise KisReadOnlyError(f"KIS_HTTP_ERROR:{exc.code}:{detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise KisReadOnlyError(f"KIS_NETWORK_ERROR:{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise KisReadOnlyError("KIS_RESPONSE_JSON_INVALID") from exc
