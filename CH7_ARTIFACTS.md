# 7장 실습 산출물 — 단일 사용자·환경별 고정계좌

## 운영 전제

- 사람 사용자: `OWNER` 한 명
- PAPER 고정계좌: `PAPER_PRIMARY`
- LIVE 고정계좌: `LIVE_PRIMARY`
- 한 프로세스에서 환경/계좌 전환 금지
- 통제 상태 버전: `control_version` 하나
- 초기 자동화: PAPER `A1`, LIVE `A0`
- 초기 실전 목표: `A2` 승인형 제출

## 추가 파일

```text
config/policy/
├─ policy_bundle.paper.yaml
├─ policy_bundle.live.yaml
├─ risk_classes.yaml
├─ automation_levels.yaml
├─ action_permissions.yaml
├─ odd.yaml
└─ kill_switch.yaml

src/kstock/
├─ policy/
│  ├─ model.py
│  ├─ loader.py
│  ├─ runtime_control.py
│  ├─ permissions.py
│  ├─ approval.py
│  ├─ odd.py
│  ├─ resume.py
│  └─ pretrade.py
├─ guard/
│  └─ risk_direction.py
├─ safety/
│  └─ kernel.py
└─ audit/
   ├─ policy_events.py
   └─ promotion_evidence.py

tests/ch07/
├─ test_policy_bundle_and_scope.py
├─ test_risk_direction_and_odd.py
├─ test_runtime_safety_and_audit.py
└─ README.md

tools/
└─ validate_ch7_policy.py
```

## 22개 시험 시나리오

7장 본문의 시험 시나리오 1~22를 동일 번호로 `tests/ch07`에 구현했다.

## 실행

```powershell
python -m pytest -q tests/ch07
python tools/validate_ch7_policy.py
python -m pytest -q
python scripts/run_checks.py
```

## 핵심 설계

1. `PolicyLoader`는 알 수 없는 action/필드/환경-계좌 불일치를 fail-closed로 거부한다.
2. `RiskClass`의 SSOT는 `risk_classes.yaml`이다.
3. 현재 자동화 수준은 호출 인자가 아니라 `RuntimeControlState.automation_profile`에서 읽는다.
4. `RiskDirection`은 제출 직전 계좌/미체결 권위 상태에서 재계산한다.
5. 승인에는 승인 당시 RiskDirection assessment hash를 바인딩한다.
6. `NO_NEW_RISK`는 INCREASE를 차단하고 축소/청산은 Recovery ODD로 제한한다.
7. `SafetyKernel`은 정책 로더와 무관하게 강화만 수행한다.
8. 실행 권한 변경 시에만 `control_version`이 증가한다.
9. `ExecutionPermit.bound_control_version`이 현재 값과 다르면 재-Guard가 필요하다.
10. `PromotionEvidence`는 감사 이벤트로부터 계산하며 수기 카운터 입력 API가 없다.
