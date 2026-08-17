# K-Stock 운영 콘솔 UI 개편 패치

## 적용 파일

- `tools/console.py` — 기존 파일 교체
- `tests/test_console_ui_contract.py` — 선택적 정적 계약 시험

## 전제

이 UI는 기존 프로젝트의 다음 모듈/도구를 그대로 사용합니다.

- `tools/console_commands.py`
- `tools/console_flows.py`
- `tools/console_state.py`
- `tools/watch_state.py`
- `tools/interest.py`

`tools/interest.py`는 KIS 관심종목을 동기화한 뒤 `watch_state`가 읽는 로컬 Watch 상태를 갱신해야 합니다.
GUI는 `.env`의 비밀값을 직접 읽지 않고 `tools/interest.py`를 별도 Python 프로세스로 호출합니다.

## 관심종목 자동 동기화

콘솔을 열면 약 0.35초 뒤 다음 명령을 자동으로 한 번 실행합니다.

```powershell
python tools/interest.py --environment PAPER --sync
```

LIVE 콘솔이면 `LIVE`가 사용됩니다.

- 동기화 성공: 왼쪽 `관심종목` 목록을 즉시 다시 표시
- 동기화 실패: 마지막 로컬 목록을 그대로 표시하고 상태만 경고
- 수동 갱신: 왼쪽 `KIS 새로고침` 버튼
- 매초/주기적 KIS polling은 하지 않음

`.env`의 실제 key 이름과 KIS 호출은 `tools/interest.py`가 소유합니다. 예전 패치 기준으로 관심종목 조회에는 `KIS_HTS_USER_ID`가 필요합니다.

## UI 변경

1. 왼쪽: KIS 관심종목/보유종목 통합 목록 + 검색
2. 가운데: `FLOWS`를 긴 스크롤 대신 탭으로 표시
3. 오른쪽: 선택 종목, 수량/가격/후보비중, 확인문구
4. 고급 입력: 기본 접힘
5. 위쪽: 환경/안전 상태 + 항상 보이는 `거래 정지`
6. 아래쪽: 실행 로그와 correlation 흐름 추적
7. 확인문구: 모든 가능한 문구를 한꺼번에 보여주지 않고, 선택한 위험 작업에 필요한 문구 하나만 표시

## 설치

기존 파일을 백업한 후:

```powershell
copy tools\console.py tools\console.py.bak
```

패치의 `tools/console.py`를 프로젝트의 같은 위치에 복사합니다.

검사:

```powershell
python -m py_compile tools\console.py
python tools\console.py --check
python -m pytest -q tests\test_console_ui_contract.py
```

실행:

```powershell
python tools\console.py
```

## 안전 계약

- GUI에서 `kstock` import 금지
- GUI에서 KIS API 직접 호출 금지
- 관심종목도 `tools/interest.py` subprocess를 통해서만 동기화
- 주문/판단 버튼은 기존 `Command` 계약 사용
- 확인 문구 자동 입력 금지
- 거래 정지는 일반 busy lock에서 제외되는 기존 `never_lock` 계약 유지
