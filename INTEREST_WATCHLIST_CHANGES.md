# KIS 관심종목 → Watch Universe

## 운영 의미

- KIS 관심종목은 `KIS_HTS_USER_ID`로 읽는다.
- 경제 상태는 현재 실행환경의 고정계좌(PAPER_PRIMARY 또는 LIVE_PRIMARY)가 계속 소유한다.
- Watch 대상은 `현재 보유종목 ∪ KIS 관심종목`이다.
- 관심목록에서 제거하더라도 보유 중인 종목은 Watch에서 빠지지 않는다.
- 관심종목 동기화는 R0 조회 기능이며 주문 권한을 만들지 않는다.

## 환경설정

`.env`에 추가:

```text
KIS_HTS_USER_ID=<본인 HTS ID>
```

PAPER에서는 PAPER App Key/App Secret, LIVE에서는 LIVE App Key/App Secret을 사용한다.

## 실행

```powershell
python tools/interest.py --environment PAPER --groups
python tools/interest.py --environment PAPER --sync
python tools/interest.py --environment PAPER --sync --group 001
python tools/interest.py --environment PAPER --show
```

CLI-First 경로도 동일하게 제공한다.

```powershell
python run_cli.py interest groups --environment PAPER --correlation-id corr_001 --output jsonl
python run_cli.py interest sync --environment PAPER --correlation-id corr_002 --output jsonl
python run_cli.py interest show --environment PAPER --correlation-id corr_003 --output jsonl
```

## 새 파일

- `src/kstock/broker/kis_readonly.py`
- `src/kstock/broker/interest.py`
- `src/kstock/interest_services.py`
- `src/kstock/watch/universe.py`
- `tools/interest.py`
- `config/watch_universe.yaml`
- `tests/test_interest_watchlist.py`
