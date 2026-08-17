from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "tools" / "console.py"


def _tree():
    return ast.parse(CONSOLE.read_text(encoding="utf-8"))


def test_console_does_not_import_kstock():
    violations = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "kstock" or alias.name.startswith("kstock."):
                    violations.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "kstock" or module.startswith("kstock."):
                violations.append((node.lineno, module))
    assert violations == []


def test_interest_sync_goes_through_tools_script():
    text = CONSOLE.read_text(encoding="utf-8")
    assert 'TOOLS / "interest.py"' in text
    assert '"--sync"' in text
    assert '"--environment"' in text
    assert "subprocess.run" in text


def test_console_does_not_embed_kis_interest_api_tr_ids():
    text = CONSOLE.read_text(encoding="utf-8")
    # KIS 네트워크 세부사항은 GUI가 아니라 tools/interest.py 아래에 있어야 한다.
    assert "HHKCM113004C7" not in text
    assert "HHKCM113004C6" not in text


def test_confirmation_is_not_prefilled_by_ui_code():
    text = CONSOLE.read_text(encoding="utf-8")
    # required phrase를 confirm StringVar에 set하는 경로를 만들지 않는다.
    assert 'fvars["confirm"].set(phrase)' not in text
