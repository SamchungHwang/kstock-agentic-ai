# Chapter 6 test scenarios

This bundle turns Chapter 6 into executable architecture contracts.

## Files

- `tools/check_layers.py` — AST-based CI checker. It never imports the application.
- `tests/ch06/test_layer_contracts.py` — static/layering scenarios 1, 2, 4, 17, 18, 19 plus current-tree gate.
- `tests/ch06/test_runtime_contracts.py` — runtime/data-contract scenarios 3, 5–16.
- `tests/ch06/test_broker_contracts.py` — runtime half of scenario 19.

## Expected public API fixed by the tests

The tests intentionally define a small stable API. Implementation code should adapt to this API rather than weakening the invariants.

### `kstock.judge.boundary`

- `BoundaryContext`
- `cross_boundary(draft, context) -> BoundaryResult`
- `BoundaryResult.status in {"PASS", "BLOCKED"}`
- `BoundaryResult.code: str`
- `BoundaryResult.thesis: InvestmentThesis | None`

### `kstock.judge.drafts`

- `InvestmentThesisDraft`
- `PredicateDraft`

Free-text invalidation text is documentary only. It is never interpreted into a numeric predicate by the boundary.

### `kstock.domain.thesis_lifecycle`

- `ThesisLifecycleState`
- `invalidate_thesis(...)`
- `supersede_thesis(...)`

The thesis contract itself remains immutable. Lifecycle status is a separate record.

### `kstock.portfolio.sizing`

- `PortfolioSnapshot`
- `size_position(...) -> SizingResult`
- identical thesis + lifecycle + snapshot + policy yields identical deterministic `decision_hash`
- `Contract.contract_hash` may still cover system-issued metadata for audit integrity

### `kstock.portfolio.proposal`

- `build_proposal(...) -> ProposalBuildResult`
- INVALIDATED thesis blocks `RiskDirection.INCREASE`
- INVALIDATED thesis permits `REDUCE` and `EXIT` review flows

### `kstock.guard`

- final `GuardStatus` is closed to `PASS` or `BLOCKED`
- authoritative-state read failure => `STATE_UNAVAILABLE/BLOCKED`
- authorization is deterministic and role-based
- unmapped recovery code => `HUMAN_REQUIRED`

### `kstock.broker`

- `derive_submission_key(intent_id)` is the sole derivation path
- adapter ignores any caller-supplied `intent.submission_key`

## Run

```bash
pytest -q tests/ch06
python tools/check_layers.py
```

A missing production API is a test failure by design. Chapter 6 is defining contracts for later chapters, not skipping unfinished code.
