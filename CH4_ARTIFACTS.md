# 4장 실습 산출물 — Console V2·V3 계약

이 패키지는 V2·V3 GUI를 구현하지 않는다. 다음 단계의 구현자가 임의로 권한·입력·승격 규칙을 추가하지 못하도록 네 개의 기계 판독 계약과 계약 시험을 고정한다.

## 산출물 1 — Console V2·V3 화면 계약
- `contracts/console_v2_v3_screen.json`
- V1/V2/V3_PAPER 패널과 권한·금지 기능 정의
- V3 제출 패널은 `intent_id`와 읽기 전용 주문정보만 표시
- 종목·수량·가격 편집 필드와 raw 주문 폼 금지

## 산출물 2 — CLI 입출력 계약
- `contracts/cli_io_contracts.json`
- `judge run`, `thesis validate`, `portfolio size`, `proposal decide`, `intent issue`, `order submit-approved`
- `order submit-approved`는 `intent_id`만 입력
- `--symbol`, `--qty`, `--price` 금지
- UNKNOWN에서 자동 재전송 금지

## 산출물 3 — 버튼–권한–위험등급 매핑표
- `contracts/button_permission_risk_map.json`
- 최소 Console 버전, 권한, 위험등급, 확인문구, always_available를 고정
- 거래 정지와 미체결 취소는 항상 사용 가능

## 산출물 4 — 단계별 기능 승격표
- `contracts/feature_promotion.json`
- V1 → V2 → V3_PAPER 기능 승격 규칙
- `BROKER_SUBMIT_PAPER`는 모든 승격 증거가 존재할 때만 활성화
- 증거가 하나라도 사라지면 즉시 비활성화
- raw order CLI와 자동 승인·자동 제출은 전 단계 금지

## 순수 계약 구현
- `src/kstock/v2v3_contracts.py`
- `src/kstock/v2v3_flow.py`

실제 LLM 또는 브로커를 호출하지 않는다. 해시·승인 이벤트·Intent 발급·제출 전 차단·중복 방지 등 V2/V3의 권한 경계를 순수 함수로 검증한다.

## 20개 시험 시나리오
- `tests/test_ch4_contracts.py`

본문의 20개 시험 시나리오를 계약 수준 자동시험으로 구현했다. 외부 LLM/KIS 실연동이 필요한 성공 경로 자체가 아니라, 4장에서 고정해야 하는 '허용/금지/입력 불변성/승격 조건'을 시험한다.

## 계약 검사

```powershell
python tools/validate_ch4_contracts.py
```

정상 결과:

```text
4장 Console V2·V3 계약 검사 통과
```

전체 시험:

```powershell
python -m pytest -q
```
