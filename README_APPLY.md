# 관심종목 1개만 표시되는 문제 수정

원인: 이전 패치가 실제 KIS 관심종목이 아니라 계좌 보유종목만 조회하고 Watch 목록을 덮어썼습니다.

이 패치는 다음을 수행합니다.

- 실제 KIS 관심종목 그룹 API 사용
- 실제 그룹별 관심종목 API 사용
- 관심종목과 보유종목을 합집합으로 표시
- 관심종목 조회 실패 시 마지막 정상 Watch 목록을 보유종목 1개로 덮어쓰지 않음
- 기존 ID 이름 호환: `KIS_ID`, `KIS_USER_ID`, `KIS_HTS_ID`, `KIS_HTS_USER_ID`, `KIS_LOGIN_ID`, `HTS_ID`, `MY_HTSID`
- KIS 공식 샘플의 `kis_devlp.yaml: my_htsid`도 지원
- 계좌번호를 관심종목 `USER_ID`로 잘못 대체하지 않음

프로젝트 루트에 덮어쓴 후:

```powershell
python -m pytest -q tests/test_interest_watchlist.py
python tools/interest.py --environment PAPER --groups
python tools/interest.py --environment PAPER --sync
python tools/interest.py --environment PAPER --show
```
