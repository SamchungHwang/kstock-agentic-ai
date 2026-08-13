# K-Stock Agentic AI 실습 코드 — 단일사용자·환경별 고정계좌

현재 1~6장 실습 산출물을 누적한 **개인투자자용 DEMO 골격**이다. PAPER와 LIVE는 서로 다른 고정계좌·상태 저장소를 사용한다.

- 안전 기동 콘솔
- 조회 패널
- 대사 패널
- 킬 스위치 패널
- 감사 추적 패널
- 거래 정지 중에도 작동하는 비상 버튼과 미체결 주문 취소

실제 KIS/OpenDART 자격증명과 네트워크 호출은 포함하지 않는다. 대신
`external_adapter.py`가 외부 경계 호출을 계측하여 빠른 점검·로컬 자동 갱신이
외부 호출을 유발하지 않는지 자동시험으로 검증한다.

## 운영 전제 — 단일 사용자, 환경별 고정계좌

이 코드의 사람 사용자는 `OWNER` 한 명뿐이다. 계좌를 선택하거나 여러 계좌를 동시에 운용하지 않는다.

- `PAPER` 실행세계 → `PAPER_PRIMARY` 고정계좌 1개
- `LIVE` 실행세계 → `LIVE_PRIMARY` 고정계좌 1개
- 한 GUI/CLI 프로세스는 PAPER 또는 LIVE 하나만 사용한다.
- 실행 중 계좌 전환 기능은 없다. 환경을 바꾸려면 새 프로세스를 시작한다.
- 실제 KIS 계좌번호는 `.env`의 환경별 자격증명에만 있고, 도메인 계약에는 논리 식별자 `PAPER_PRIMARY`/`LIVE_PRIMARY`를 사용한다.
- PAPER와 LIVE의 상태·감사·저장본은 각각 `data/paper/`, `data/live/` 아래에 분리된다.
- 내부 worker와 `SYSTEM_GUARDIAN`은 사람 사용자가 아니라 서비스 actor다.

Windows 실행 예:

```bat
run_console_paper.bat
run_console_live.bat
```

또는:

```bat
run_console.bat --environment PAPER
run_console.bat --environment LIVE
```


## v3의 주요 보완

- 새 Console 세션 시작 시 이전 `OPEN` 게이트를 `CLOSED`로 강제 전환
- 빠른 점검과 전체 점검의 외부 경계 호출 분리
- 대사 `MATCH`·`MISMATCH`·`UNKNOWN` 구현
- 게이트 열기 전 최신 전체 점검·감사 쓰기 가능 여부 재검사
- 감사 기록 실패 시 게이트 열기·재가동 차단 및 실패 시 롤백
- 거래 정지 중 계좌 조회·대사·미체결 주문 취소 허용
- 거래정지 시세의 `display_price`·`risk_price` 분리
- 저장본 공시 재현의 결정론적 `normalized_hash`
- JSON 결과와 종료 코드 계약 검사 함수화
- 모든 흐름에 `correlation_id` 전달
- 화면 로그 지우기 버튼과 `Ctrl+L`
- 본문 시험 시나리오와 직접 대응하는 20개 자동시험

## 실행

Windows(PAPER 기본):

```bat
run_console.bat --environment PAPER
```

LIVE는 별도 새 프로세스로 시작한다.

```bat
run_console.bat --environment LIVE
```

## 권장 실습 순서

1. 프로그램을 실행한다. 이전 세션이 `OPEN`이어도 새 세션은 `CLOSED`로 시작한다.
2. `대사` 탭에서 **대사 MATCH 주입** 후 **대사 실행**을 누른다.
3. `안전 기동` 탭에서 **전체 점검**을 실행한다.
4. **게이트 열기**를 누르고 `START TRADING`을 입력한다.
5. `대사` 탭에서 **대사 MISMATCH 주입** 후 **대사 실행**을 누른다.
6. 게이트 `HALTED`, 킬 스위치 `ON`을 확인한다.
7. **데모 복구**에 `CONFIRM`을 입력하고, 다시 **대사 실행**과 **전체 점검**을 실행한다.
8. `킬 스위치` 탭에서 재가동 사유와 `RESUME TRADING`을 입력한다.
9. 감사 탭에서 같은 `correlation_id`의 대사·킬 스위치·게이트 이벤트를 추적한다.

## 비상 기능

화면 하단의 **거래 정지**와 **미체결 주문 취소**는 다른 명령의 잠금 그룹과
독립적으로 실행된다. Console V1에는 주문 제출 기능이 없으며, CLI의
`order submit`은 `OUT_OF_SCOPE_CONSOLE_V1`로 명시적으로 차단한다.

## 자동시험

```bash
python -m pytest -q
```

현재 기준: **133건 통과**. 이 중 `tests/test_scenarios.py`의 20건이
`TEST_SCENARIOS.md`와 번호별로 대응한다.

## 핵심 파일

- `src/kstock/console_app.py`: Tkinter 화면과 패널·비상 버튼
- `src/kstock/console_commands.py`: 검증된 `CommandSpec`
- `src/kstock/console_runner.py`: `subprocess.Popen(argv, shell=False)`와 JSONL 계약 검사
- `src/kstock/console_v1_cli.py`: 모든 버튼이 호출하는 CLI
- `src/kstock/demo_services.py`: Console V1 데모 서비스와 안전 상태 전이
- `src/kstock/external_adapter.py`: 외부 경계 호출 계측용 DEMO 어댑터
- `src/kstock/state_store.py`: 게이트·킬 스위치·대사·전체 점검·주문 상태
- `src/kstock/audit_store.py`: 감사 JSONL, 쓰기 건강도, 실패 주입
- `tests/test_scenarios.py`: 20개 시험 시나리오

## Windows 한글 깨짐 방지

`run_console.bat`는 코드페이지와 Python 표준 입출력을 UTF-8로 고정한다.
CLI와 GUI 사이 JSONL은 ASCII-safe JSON으로 전달되므로 한글이 깨지지 않는다.

## 화면 로그 지우기

실행 로그 오른쪽 위의 **화면 로그 지우기** 또는 `Ctrl+L`을 사용한다.
화면만 비우며 `data/paper/audit.jsonl` 또는 `data/live/audit.jsonl`과 correlation 추적 기록은 유지한다.

## v4: 동명 `kstock` 패키지 충돌 방지

CLI는 이제 `python run_cli.py` 대신 프로젝트 루트의 `run_cli.py`를 통해 실행합니다.
현재 작업 디렉터리나 가상환경에 예전 `kstock` 패키지가 있어도 이 프로젝트의
`src/kstock/console_v1_cli.py`를 우선 선택합니다.

직접 CLI를 시험할 때도 다음 형식을 사용하십시오.

```powershell
python .\run_cli.py startup session-init --environment PAPER --correlation-id corr_test --output jsonl
python .\run_cli.py order submit --environment PAPER --correlation-id corr_test --output jsonl
```

## v6: KIS 환경변수 이름 통일

프로젝트 루트의 `.env.example`을 `.env`로 복사하고 모의투자 값을 입력한다.

```powershell
Copy-Item .env.example .env
```

Console V1은 다음 이름을 사용한다.

```text
KIS_PAPER_APP_KEY
KIS_PAPER_APP_SECRET
KIS_PAPER_ACCOUNT
KIS_PAPER_ACCOUNT_PRODUCT

KIS_LIVE_APP_KEY
KIS_LIVE_APP_SECRET
KIS_LIVE_ACCOUNT
KIS_LIVE_ACCOUNT_PRODUCT
KIS_ALLOW_LIVE
```

계좌는 `50012345-01`처럼 한 칸에 입력하거나, 계좌 8자리와 상품코드 2자리를
각각 입력할 수 있다. `.env`는 저장소에 커밋하지 않는다.

환경변수 형식 확인:

```powershell
python .\tools\doctor_env.py --environment PAPER
```

빠른 점검은 `.env`를 로컬에서만 검사하며 외부 API를 호출하지 않는다.
전체 점검과 계좌·매수가능금액 조회는 환경변수가 누락되거나 형식이 잘못되면
`KIS_ENV_INVALID`로 차단한다. 앱키와 시크릿 원문은 JSONL·감사 로그·화면에
출력하지 않는다.
