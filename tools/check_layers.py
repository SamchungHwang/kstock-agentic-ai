from __future__ import annotations

"""Chapter 6 architecture-boundary checks.

The checker deliberately uses the Python AST instead of importing application
modules. This keeps CI safe even when the application is only partially built.

Usage:
    python tools/check_layers.py

Exit codes:
    0: all architecture rules pass
    1: one or more violations were found
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


LLM_PROVIDER_PREFIXES: tuple[str, ...] = (
    "openai",
    "anthropic",
    "litellm",
    "ollama",
    "cohere",
    "mistralai",
    "google.generativeai",
    "google.genai",
)

KIS_PROVIDER_PREFIXES: tuple[str, ...] = (
    "mojito",
    "pykis",
    "korea_investment",
    "kis_devlp",
)

BROKER_SUBMIT_NAMES = {"submit_order", "place_order", "broker_submit"}
RAW_SYMBOL_NAMES = {"symbol", "ticker", "security_id"}
RAW_QTY_NAMES = {"qty", "quantity", "order_qty"}
RAW_PRICE_NAMES = {"price", "limit_price", "order_price"}


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.rule}] {location} - {self.detail}"


def _project_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[1]


def _src_root(root: Path | str | None = None) -> Path:
    return _project_root(root) / "src" / "kstock"


def _python_files(base: Path) -> Iterator[Path]:
    if not base.exists():
        return iter(())
    return (p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _imported_modules(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module, node.lineno


def _matches_prefix(module: str, prefixes: Sequence[str]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    result: set[str] = set()
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            result.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            result.add(dec.attr)
        elif isinstance(dec, ast.Call):
            target = dec.func
            if isinstance(target, ast.Name):
                result.add(target.id)
            elif isinstance(target, ast.Attribute):
                result.add(target.attr)
    return result


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _attribute_chain(node: ast.AST) -> str:
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def check_llm_only_in_judge(root: Path | str | None = None) -> list[Violation]:
    """LLM provider imports are legal only under src/kstock/judge/."""
    root_path = _project_root(root)
    src = _src_root(root)
    judge = src / "judge"
    violations: list[Violation] = []

    for path in _python_files(src):
        if _is_under(path, judge):
            continue
        tree = _parse(path)
        for module, line in _imported_modules(tree):
            if _matches_prefix(module, LLM_PROVIDER_PREFIXES):
                violations.append(
                    Violation(
                        "LLM_ONLY_IN_JUDGE",
                        _rel(path, root_path),
                        line,
                        f"LLM provider import '{module}' is outside kstock.judge",
                    )
                )
    return violations


def check_single_cross_boundary(root: Path | str | None = None) -> list[Violation]:
    """Exactly one cross_boundary definition must exist, in judge/boundary.py."""
    root_path = _project_root(root)
    src = _src_root(root)
    expected = (src / "judge" / "boundary.py").resolve()
    found: list[tuple[Path, int]] = []

    for path in _python_files(src):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "cross_boundary":
                found.append((path.resolve(), node.lineno))

    violations: list[Violation] = []
    if not found:
        return [
            Violation(
                "SINGLE_CROSS_BOUNDARY",
                _rel(expected, root_path),
                0,
                "cross_boundary is missing",
            )
        ]

    for path, line in found:
        if path != expected:
            violations.append(
                Violation(
                    "SINGLE_CROSS_BOUNDARY",
                    _rel(path, root_path),
                    line,
                    "cross_boundary may exist only in kstock.judge.boundary",
                )
            )

    if len(found) != 1:
        path, line = found[0]
        violations.append(
            Violation(
                "SINGLE_CROSS_BOUNDARY",
                _rel(path, root_path),
                line,
                f"expected exactly one cross_boundary definition, found {len(found)}",
            )
        )
    return violations


def check_no_broker_import_from_portfolio(root: Path | str | None = None) -> list[Violation]:
    """Portfolio cannot depend on broker packages or direct KIS clients."""
    root_path = _project_root(root)
    portfolio = _src_root(root) / "portfolio"
    violations: list[Violation] = []

    for path in _python_files(portfolio):
        tree = _parse(path)
        for module, line in _imported_modules(tree):
            broker_import = module == "kstock.broker" or module.startswith("kstock.broker.")
            kis_import = _matches_prefix(module, KIS_PROVIDER_PREFIXES)
            if broker_import or kis_import:
                violations.append(
                    Violation(
                        "PORTFOLIO_NO_BROKER",
                        _rel(path, root_path),
                        line,
                        f"portfolio must not import '{module}'",
                    )
                )
    return violations


def check_guard_does_not_import_portfolio(root: Path | str | None = None) -> list[Violation]:
    """Guard cannot import judge, portfolio, or broker."""
    root_path = _project_root(root)
    guard = _src_root(root) / "guard"
    forbidden = ("kstock.judge", "kstock.portfolio", "kstock.broker")
    violations: list[Violation] = []

    for path in _python_files(guard):
        tree = _parse(path)
        for module, line in _imported_modules(tree):
            if any(module == p or module.startswith(p + ".") for p in forbidden):
                violations.append(
                    Violation(
                        "GUARD_NO_REVERSE_IMPORT",
                        _rel(path, root_path),
                        line,
                        f"guard must not import '{module}'",
                    )
                )
    return violations


def check_guard_has_no_llm_dependency(root: Path | str | None = None) -> list[Violation]:
    root_path = _project_root(root)
    guard = _src_root(root) / "guard"
    violations: list[Violation] = []

    for path in _python_files(guard):
        tree = _parse(path)
        for module, line in _imported_modules(tree):
            if _matches_prefix(module, LLM_PROVIDER_PREFIXES):
                violations.append(
                    Violation(
                        "GUARD_NO_LLM",
                        _rel(path, root_path),
                        line,
                        f"guard must not import LLM provider '{module}'",
                    )
                )
    return violations


def check_single_broker_submitter(root: Path | str | None = None) -> list[Violation]:
    """One concrete broker submitter is allowed, and it must live under broker/."""
    root_path = _project_root(root)
    src = _src_root(root)
    broker = src / "broker"
    concrete: list[tuple[Path, int, str]] = []
    violations: list[Violation] = []

    for path in _python_files(src):
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in BROKER_SUBMIT_NAMES:
                continue
            if "abstractmethod" in _decorator_names(node):
                continue
            concrete.append((path, node.lineno, node.name))
            if not _is_under(path, broker):
                violations.append(
                    Violation(
                        "SINGLE_BROKER_SUBMITTER",
                        _rel(path, root_path),
                        node.lineno,
                        f"concrete broker submitter '{node.name}' is outside kstock.broker",
                    )
                )

    broker_defs = [item for item in concrete if _is_under(item[0], broker)]
    if len(broker_defs) != 1:
        path = broker_defs[0][0] if broker_defs else broker / "adapter.py"
        line = broker_defs[0][1] if broker_defs else 0
        violations.append(
            Violation(
                "SINGLE_BROKER_SUBMITTER",
                _rel(path, root_path),
                line,
                f"expected exactly one concrete broker submitter under kstock.broker, found {len(broker_defs)}",
            )
        )
    return violations


def _function_arg_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    return {arg.arg for arg in args}


def _argparse_options(tree: ast.AST) -> set[str]:
    options: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                raw = arg.value.lstrip("-").replace("-", "_")
                options.add(raw)
    return options


def _contains_raw_triplet(names: set[str]) -> bool:
    return bool(names & RAW_SYMBOL_NAMES) and bool(names & RAW_QTY_NAMES) and bool(names & RAW_PRICE_NAMES)


def check_no_raw_order_cli(root: Path | str | None = None) -> list[Violation]:
    """A CLI must never expose raw symbol+qty+price submission parameters."""
    root_path = _project_root(root)
    cli = _src_root(root) / "cli"
    violations: list[Violation] = []

    for path in _python_files(cli):
        tree = _parse(path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = _function_arg_names(node)
                commandish = any(token in node.name.lower() for token in ("submit", "order", "buy", "sell", "place"))
                if commandish and _contains_raw_triplet(names):
                    violations.append(
                        Violation(
                            "NO_RAW_ORDER_CLI",
                            _rel(path, root_path),
                            node.lineno,
                            "CLI order command exposes raw symbol/qty/price",
                        )
                    )

        argparse_names = _argparse_options(tree)
        if _contains_raw_triplet(argparse_names):
            violations.append(
                Violation(
                    "NO_RAW_ORDER_CLI",
                    _rel(path, root_path),
                    1,
                    "argparse CLI exposes raw symbol/qty/price together",
                )
            )
    return violations


def check_broker_derives_submission_key(root: Path | str | None = None) -> list[Violation]:
    """Broker submitter must derive submission_key from intent_id, never trust intent.submission_key."""
    root_path = _project_root(root)
    broker = _src_root(root) / "broker"
    violations: list[Violation] = []
    derive_call_found = False

    for path in _python_files(broker):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "submission_key":
                chain = _attribute_chain(node)
                head = chain.split(".", 1)[0]
                if head in {"intent", "order_intent", "proposal"}:
                    violations.append(
                        Violation(
                            "BROKER_DERIVES_SUBMISSION_KEY",
                            _rel(path, root_path),
                            getattr(node, "lineno", 0),
                            f"broker must not trust caller-provided '{chain}'",
                        )
                    )

            if isinstance(node, ast.Call) and _call_name(node) == "derive_submission_key":
                for arg in node.args:
                    text = ast.unparse(arg)
                    if "intent_id" in text:
                        derive_call_found = True

    if not derive_call_found:
        violations.append(
            Violation(
                "BROKER_DERIVES_SUBMISSION_KEY",
                _rel(broker / "adapter.py", root_path),
                0,
                "no derive_submission_key(...intent_id...) call found under kstock.broker",
            )
        )
    return violations


def check_invalidation_cannot_create_order(root: Path | str | None = None) -> list[Violation]:
    """Invalidation evaluator may emit reevaluation only, never execution contracts."""
    root_path = _project_root(root)
    path = _src_root(root) / "watch" / "invalidation.py"
    if not path.exists():
        return []

    forbidden = {"OrderIntent", "OrderProposal", "BrokerRequest", "BrokerSubmission"}
    tree = _parse(path)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in forbidden:
                violations.append(
                    Violation(
                        "INVALIDATION_NO_ORDER",
                        _rel(path, root_path),
                        node.lineno,
                        f"invalidation evaluator must not create {name}",
                    )
                )
    return violations


def check_judge_cannot_create_execution_contracts(root: Path | str | None = None) -> list[Violation]:
    """Judge may create OrderProposal only at the boundary and never OrderIntent/BrokerRequest."""
    root_path = _project_root(root)
    judge = _src_root(root) / "judge"
    boundary = (judge / "boundary.py").resolve()
    violations: list[Violation] = []

    for path in _python_files(judge):
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in {"OrderIntent", "BrokerRequest", "BrokerSubmission"}:
                violations.append(
                    Violation(
                        "JUDGE_NO_EXECUTION_CONTRACT",
                        _rel(path, root_path),
                        node.lineno,
                        f"judge must not create {name}",
                    )
                )
            elif name == "OrderProposal" and path.resolve() != boundary:
                violations.append(
                    Violation(
                        "JUDGE_NO_EXECUTION_CONTRACT",
                        _rel(path, root_path),
                        node.lineno,
                        "OrderProposal may be issued only by cross_boundary in judge/boundary.py",
                    )
                )
    return violations


def run_all_checks(root: Path | str | None = None) -> list[Violation]:
    checks = (
        check_llm_only_in_judge,
        check_single_cross_boundary,
        check_no_broker_import_from_portfolio,
        check_guard_does_not_import_portfolio,
        check_guard_has_no_llm_dependency,
        check_single_broker_submitter,
        check_no_raw_order_cli,
        check_broker_derives_submission_key,
        check_invalidation_cannot_create_order,
        check_judge_cannot_create_execution_contracts,
    )
    violations: list[Violation] = []
    for check in checks:
        violations.extend(check(root))
    return violations


def main() -> int:
    violations = run_all_checks()
    if not violations:
        print("Chapter 6 architecture checks: PASS")
        return 0

    print("Chapter 6 architecture checks: FAIL")
    for violation in violations:
        print(f" - {violation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
