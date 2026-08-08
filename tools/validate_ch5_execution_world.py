#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kstock.execution_world import (  # noqa: E402
    validate_core_entities_contract,
    validate_execution_world_contract,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    core = _load(ROOT / "config" / "domain" / "core_entities.yaml")
    world = _load(ROOT / "config" / "domain" / "execution_world.yaml")
    canvas = _load(ROOT / "contracts" / "execution_world_canvas.json")

    validate_core_entities_contract(core)
    validate_execution_world_contract(world)

    axes = set(canvas.get("axes", {}))
    required_axes = {
        "entity", "state", "transition", "constraint", "time",
        "market", "actor", "authority", "commit",
    }
    if axes != required_axes:
        raise SystemExit(f"캔버스 축 불일치: {sorted(axes)}")

    print("5장 실행 세계 계약 검사 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
