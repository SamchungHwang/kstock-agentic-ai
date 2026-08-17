# Chapter 7 contract tests

단일 사용자(OWNER) + 환경별 고정계좌(PAPER_PRIMARY/LIVE_PRIMARY) 전제의 7장 계약을 검증한다.

- `test_policy_bundle_and_scope.py`: 정책 로더, RiskClass SSOT, 고정계좌, 자동화 수준, OWNER 승인
- `test_risk_direction_and_odd.py`: RiskDirection 재계산, 승인 바인딩, ODD/Recovery ODD
- `test_runtime_safety_and_audit.py`: control_version, Safety Kernel, 재가동, PromotionEvidence, 감사 필드

실행:

```powershell
python -m pytest -q tests/ch07
python tools/validate_ch7_policy.py
```
