# 5장 실습 산출물 — K-Stock 실행 세계

이 패치는 5장의 세 산출물을 실행 가능한 계약으로 고정합니다. 완성 DB나 주문 엔진은 아닙니다.

## 산출물 1 — 실행 세계 캔버스
- `contracts/execution_world_canvas.json`
- Entity / State / Transition / Constraint / Time / Market / Actor / Authority / Commit 축
- Broker / Ledger / Policy Bundle / Audit 권위 분리
- Observation → Judgment → Proposal → Control Commit → Economic Commit → Reconciliation 흐름

## 산출물 2 — 핵심 엔티티 목록
- `config/domain/core_entities.yaml`
- JSON-compatible YAML 1.2라 외부 YAML 라이브러리 없이 `json`으로 읽을 수 있습니다.
- Issuer, Security, Account, Position, InvestmentThesis, Order, Approval의 ID와 권위 경계를 고정합니다.

## 산출물 3 — 상태·전이·제약 초안
- `config/domain/execution_world.yaml`
- 주문 상태 머신과 허용 사건을 데이터로 고정합니다.
- `SUBMITTING + TIMEOUT -> UNKNOWN`을 명시합니다.
- 신규 위험, 감사, 대사, 환경, 원시 주문 CLI 관련 불변조건을 명시합니다.

## 실행 코드
- `src/kstock/execution_world.py`
- 컨텍스트/권위 스냅숏 분리
- 주문 전이 검사 (`IllegalTransition`)
- 신규 위험 제약 검사
- 대사 결과 모델
- 통제 커밋 / 경제적 커밋 분리
- correlation_id 추적
- 계약 파일 검증

## 계약 검사

```powershell
python tools\validate_ch5_execution_world.py
```

정상:

```text
5장 실행 세계 계약 검사 통과
```

## 시험

```powershell
python -m pytest -q tests\test_ch5_execution_world.py
```

`test_ch5_execution_world.py`의 20개 테스트는 본문 5장 시험 시나리오 1~20과 번호가 일치합니다.
