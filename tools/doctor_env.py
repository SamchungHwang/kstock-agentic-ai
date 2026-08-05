#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kstock.env_config import doctor_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="KIS 환경변수 점검")
    parser.add_argument("--environment", choices=["PAPER", "LIVE"], default="PAPER")
    args = parser.parse_args()

    result = doctor_environment(args.environment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
