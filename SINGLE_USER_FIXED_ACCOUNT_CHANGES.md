# 단일사용자·환경별 고정계좌 개정 요약

## 공식 운영 범위

- 사람 사용자: `OWNER` 1명
- PAPER: `PAPER_PRIMARY` 고정계좌 1개
- LIVE: `LIVE_PRIMARY` 고정계좌 1개
- 한 프로세스는 PAPER 또는 LIVE 하나만 사용
- 실행 중 계좌 선택/전환 없음
- 실행 중 환경 전환 없음. 다른 환경은 새 프로세스로 시작
- 내부 worker / `SYSTEM_GUARDIAN`은 사람 사용자가 아니라 service actor

## 핵심 변경

1. `src/kstock/fixed_identity.py` 추가
   - `OWNER_ACTOR_ID`
   - `PAPER_PRIMARY`, `LIVE_PRIMARY`
   - 환경↔고정계좌 binding 검증

2. GUI/CLI에서 계좌 입력 제거
   - `account_alias` 제거
   - 환경은 프로세스 시작 인자로만 선택
   - 화면에는 선택 UI 대신 고정 환경·계좌를 표시

3. PAPER/LIVE 런타임 데이터 분리
   - `data/paper/`
   - `data/live/`
   - 상태, 감사, 저장본이 서로 섞이지 않음

4. 사람 역할 단순화
   - `APPROVER`, `SUBMITTER` 사람 역할 제거
   - 사람은 `OWNER` 하나
   - OWNER가 승인하고 승인된 작업을 service worker가 실행하는 것은 허용 가능

5. Chapter 4/5 계약에 고정 계좌 binding 반영
   - `OrderIntent.account_ref` 추가
   - PAPER intent는 `PAPER_PRIMARY`, LIVE는 `LIVE_PRIMARY`
   - 실행 세계 config에 단일 사용자·고정계좌 불변조건 추가

6. 환경 전환 제한
   - 서비스 계층이 현재 프로세스와 다른 환경을 요청하면 `RUNTIME_ENVIRONMENT_SWITCH_FORBIDDEN`
   - PAPER↔LIVE 전환은 새 GUI/CLI 프로세스로 수행

## 실행

```powershell
run_console_paper.bat
```

또는

```powershell
run_console_live.bat
```

명시형:

```powershell
run_console.bat --environment PAPER
run_console.bat --environment LIVE
```

## 검증 결과

```text
133 passed
Chapter 6 architecture checks: PASS
4장 Console V2·V3 계약 검사 통과
5장 실행 세계 계약 검사 통과
```
