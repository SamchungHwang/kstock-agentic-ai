# Architecture

```text
OWNER 1명
  ↓ 클릭·직접 입력
K-Stock Console [PAPER 또는 LIVE 고정]
  ↓ CommandSpec
검증된 CLI
  ↓
Application Service / Domain / Guard / Adapter
  ↓
PAPER → PAPER_PRIMARY
LIVE  → LIVE_PRIMARY
  ↓
내부 원장·감사 저장소·OpenDART·한국투자증권
```

- 사람 사용자는 `OWNER` 한 명뿐이다.
- PAPER와 LIVE는 서로 다른 고정계좌를 가진다.
- 한 프로세스에서는 계좌와 환경을 전환하지 않는다.
- 내부 worker와 `SYSTEM_GUARDIAN`은 사람 사용자가 아니라 service actor다.
- `tools/console.py`와 `tools/console_commands.py`는 `kstock`을 임포트하지 않는다.
- 콘솔은 투자 계층이 아니라 검증된 명령을 요청하는 운영 표면이다.
