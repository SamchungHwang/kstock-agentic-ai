"""Fail when authority-free console modules import kstock."""
from __future__ import annotations
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATHS = [ROOT / "tools/console.py", ROOT / "tools/console_commands.py"]

def imports_kstock(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "kstock" or alias.name.startswith("kstock."):
                    out.append(f"{path.relative_to(ROOT)}:{node.lineno}: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "kstock" or module.startswith("kstock."):
                out.append(f"{path.relative_to(ROOT)}:{node.lineno}: {module}")
    return out

def check() -> list[str]:
    return [v for path in PATHS for v in imports_kstock(path)]

def main() -> int:
    violations = check()
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("OK: GUI import boundary intact")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
