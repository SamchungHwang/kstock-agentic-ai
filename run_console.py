#!/usr/bin/env python3
"""Console V1 실행 진입점."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
SRC_TEXT = str(SRC)

# 현재 작업 디렉터리나 설치된 동명 패키지보다 이 프로젝트의 src를 우선한다.
sys.path[:] = [item for item in sys.path if item != SRC_TEXT]
sys.path.insert(0, SRC_TEXT)

# 프로젝트 루트 .env를 먼저 읽는다. 실제 OS 환경변수가 있으면 그것을 우선한다.
from kstock.env_config import load_dotenv_file

load_dotenv_file(ROOT / ".env", override=False)

from kstock.console_app import main


if __name__ == "__main__":
    raise SystemExit(main())
