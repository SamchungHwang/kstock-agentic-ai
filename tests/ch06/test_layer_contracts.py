from __future__ import annotations

"""Chapter 6 - architecture boundary tests.

These tests verify both:
1) the checker catches deliberately injected violations, and
2) the current repository tree has no Chapter 6 architecture violation.
"""

from pathlib import Path

import pytest

from tools.check_layers import (
    check_broker_derives_submission_key,
    check_guard_does_not_import_portfolio,
    check_invalidation_cannot_create_order,
    check_judge_cannot_create_execution_contracts,
    check_llm_only_in_judge,
    check_no_broker_import_from_portfolio,
    check_single_cross_boundary,
    run_all_checks,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _minimal_tree(tmp_path: Path) -> Path:
    """Create the minimum legal tree needed by the architecture checker."""
    _write(
        tmp_path,
        "src/kstock/judge/boundary.py",
        "def cross_boundary(draft):\n    return draft\n",
    )
    _write(
        tmp_path,
        "src/kstock/broker/idempotency.py",
        "def derive_submission_key(intent_id):\n    return 'k:' + str(intent_id)\n",
    )
    _write(
        tmp_path,
        "src/kstock/broker/adapter.py",
        "from .idempotency import derive_submission_key\n\n"
        "def submit_order(intent):\n"
        "    key = derive_submission_key(intent.intent_id)\n"
        "    return key\n",
    )
    _write(tmp_path, "src/kstock/watch/invalidation.py", "def evaluate(x):\n    return None\n")
    return tmp_path


# Scenario 1

def test_01_watch_llm_provider_import_is_rejected(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/watch/collector.py", "from openai import OpenAI\n")

    violations = check_llm_only_in_judge(root)

    assert violations
    assert any(v.rule == "LLM_ONLY_IN_JUDGE" for v in violations)


# Scenario 2
@pytest.mark.parametrize(
    ("path", "source"),
    [
        (
            "src/kstock/judge/model_port.py",
            "def make_proposal():\n    return OrderProposal(symbol='005930')\n",
        ),
        (
            "src/kstock/judge/model_port.py",
            "def make_intent():\n    return OrderIntent(symbol='005930', qty=1)\n",
        ),
    ],
)
def test_02_judge_direct_execution_contract_path_is_rejected(
    tmp_path: Path,
    path: str,
    source: str,
) -> None:
    root = _minimal_tree(tmp_path)
    _write(root, path, source)

    violations = check_judge_cannot_create_execution_contracts(root)

    assert violations
    assert any(v.rule == "JUDGE_NO_EXECUTION_CONTRACT" for v in violations)


# Scenario 4

def test_04_second_cross_boundary_definition_is_rejected(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/judge/model_port.py", "def cross_boundary(x):\n    return x\n")

    violations = check_single_cross_boundary(root)

    assert violations
    assert any(v.rule == "SINGLE_CROSS_BOUNDARY" for v in violations)


# Scenario 17

def test_17_guard_importing_portfolio_is_rejected(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/guard/decision.py", "from kstock.portfolio.sizing import size_position\n")

    violations = check_guard_does_not_import_portfolio(root)

    assert violations
    assert any(v.rule == "GUARD_NO_REVERSE_IMPORT" for v in violations)


# Scenario 18
@pytest.mark.parametrize("module", ["kstock.broker.adapter", "pykis", "mojito"])
def test_18_portfolio_importing_broker_or_kis_is_rejected(tmp_path: Path, module: str) -> None:
    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/portfolio/sizing.py", f"import {module}\n")

    violations = check_no_broker_import_from_portfolio(root)

    assert violations
    assert any(v.rule == "PORTFOLIO_NO_BROKER" for v in violations)


# Scenario 19 - static half

def test_19_broker_cannot_trust_intent_submission_key(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    _write(
        root,
        "src/kstock/broker/adapter.py",
        "def submit_order(intent):\n"
        "    submission_key = intent.submission_key\n"
        "    return submission_key\n",
    )

    violations = check_broker_derives_submission_key(root)

    assert violations
    assert any(v.rule == "BROKER_DERIVES_SUBMISSION_KEY" for v in violations)


# Invalidation rule backing scenarios around Chapter 6 safety boundary.

def test_invalidation_evaluator_cannot_create_order_contract(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    _write(
        root,
        "src/kstock/watch/invalidation.py",
        "def evaluate(event):\n    return OrderIntent(symbol='005930', qty=1)\n",
    )

    violations = check_invalidation_cannot_create_order(root)

    assert violations
    assert any(v.rule == "INVALIDATION_NO_ORDER" for v in violations)


# Repository-level CI gate.

def test_current_repository_passes_chapter6_layer_contracts() -> None:
    violations = run_all_checks(REPO_ROOT)
    assert violations == [], "\n" + "\n".join(str(v) for v in violations)

# Named CI-check regression tests from Chapter 6 deliverable 3.

def test_check_guard_has_no_llm_dependency_detects_provider_import(tmp_path: Path) -> None:
    from tools.check_layers import check_guard_has_no_llm_dependency

    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/guard/preflight.py", "from anthropic import Anthropic\n")

    violations = check_guard_has_no_llm_dependency(root)
    assert any(v.rule == "GUARD_NO_LLM" for v in violations)


def test_check_single_broker_submitter_rejects_second_submitter(tmp_path: Path) -> None:
    from tools.check_layers import check_single_broker_submitter

    root = _minimal_tree(tmp_path)
    _write(root, "src/kstock/broker/secondary.py", "def submit_order(intent):\n    return intent\n")

    violations = check_single_broker_submitter(root)
    assert any(v.rule == "SINGLE_BROKER_SUBMITTER" for v in violations)


def test_check_no_raw_order_cli_rejects_symbol_qty_price_command(tmp_path: Path) -> None:
    from tools.check_layers import check_no_raw_order_cli

    root = _minimal_tree(tmp_path)
    _write(
        root,
        "src/kstock/cli/order.py",
        "def submit_order(symbol: str, qty: int, price: int):\n    return None\n",
    )

    violations = check_no_raw_order_cli(root)
    assert any(v.rule == "NO_RAW_ORDER_CLI" for v in violations)
