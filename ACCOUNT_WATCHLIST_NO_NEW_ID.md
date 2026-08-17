# 기존 `.env`만 사용하는 계좌 종목 동기화

## 변경 원칙

- `KIS_HTS_ID`, `KIS_HTS_USER_ID`, `KIS_USER_ID`를 읽지 않는다.
- 기존 환경변수만 사용한다.
  - `KIS_PAPER_APP_KEY`
  - `KIS_PAPER_APP_SECRET`
  - `KIS_PAPER_ACCOUNT`
  - `KIS_PAPER_ACCOUNT_PRODUCT`
  - LIVE 환경에서는 대응하는 `KIS_LIVE_*`
- 별도 HTS 관심그룹 API 대신 현재 고정계좌의 주식잔고를 조회한다.
- 기존 UI/CLI 호환을 위해 `interest groups/sync/show` 명령 이름은 유지한다.
- `--groups`는 `ACCOUNT / 계좌 보유종목` 한 개를 반환한다.

## 실행

```powershell
python tools/interest.py --environment PAPER --groups
python tools/interest.py --environment PAPER --sync
python tools/interest.py --environment PAPER --show
```

더 이상 `KIS_HTS_ID_MISSING` 오류가 발생해서는 안 된다.
