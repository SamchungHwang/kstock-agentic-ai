"""Backend CLI placeholder. Actual commands are added in later chapters."""
from __future__ import annotations
import json
import sys
from typing import Sequence

def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print(json.dumps({
        "kind": "result",
        "status": "ERROR",
        "code": "COMMAND_NOT_IMPLEMENTED",
        "message": "백엔드 CLI는 다음 장에서 구현합니다.",
        "argv": args,
        "next_action": "CLI 구현과 계약 시험을 먼저 추가하십시오."
    }, ensure_ascii=False))
    return 20

if __name__ == "__main__":
    raise SystemExit(main())
