#!/usr/bin/env python3
"""Console V1 전용 CLI 진입점.

기존 K-Stock 프로젝트에는 ``src/kstock/cli/`` 패키지가 이미 있을 수 있다.
따라서 ``kstock.cli``라는 이름을 재사용하지 않고, 충돌하지 않는
``kstock.console_v1_cli`` 모듈을 명시적으로 실행한다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
SRC_TEXT = str(SRC)
EXPECTED_MODULE = (SRC / "kstock" / "console_v1_cli.py").resolve()

# 현재 프로젝트의 src를 최우선으로 둔다.
sys.path[:] = [item for item in sys.path if item != SRC_TEXT]
sys.path.insert(0, SRC_TEXT)

# 프로젝트 루트 .env를 먼저 읽는다. 실제 OS 환경변수가 있으면 그것을 우선한다.
from kstock.env_config import load_dotenv_file

load_dotenv_file(ROOT / ".env", override=False)

module = importlib.import_module("kstock.console_v1_cli")
loaded_from = Path(module.__file__).resolve()
if loaded_from != EXPECTED_MODULE:
    raise ImportError(
        "Console V1 CLI를 잘못된 위치에서 불러왔습니다. "
        f"expected={EXPECTED_MODULE}, loaded={loaded_from}"
    )

main = module.main


if __name__ == "__main__":
    raise SystemExit(main())
