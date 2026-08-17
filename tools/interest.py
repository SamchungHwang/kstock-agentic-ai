"""KIS 관심종목을 K-Stock Watch 대상으로 동기화한다.

    python tools/interest.py --environment PAPER --groups
    python tools/interest.py --environment PAPER --sync
    python tools/interest.py --environment PAPER --sync --group 001
    python tools/interest.py --environment PAPER --show

관심종목은 KIS HTS 사용자 ID에 저장된 그룹/종목 목록이다. K-Stock은 이를
현재 고정계좌 보유종목과 합쳐 Watch Universe를 만든다. 관심목록에서 종목을
삭제해도 실제 보유 중이면 감시 대상에서 빠지지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kstock.interest_services import (  # noqa: E402
    current_watch_universe,
    interest_groups_query,
    sync_interest_watchlist,
)
from kstock.state_store import configure_runtime_environment  # noqa: E402


def _print_result(result) -> int:
    print(f"[{result.status.value}] {result.code} — {result.message}")
    if result.payload:
        print(json.dumps(result.payload, ensure_ascii=False, indent=2))
    if result.next_action:
        print(f"\n다음 조치: {result.next_action}")
    return 0 if result.status.value == "SUCCESS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="KIS 관심종목 → K-Stock Watch Universe")
    parser.add_argument("--environment", choices=["PAPER", "LIVE"], required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--groups", action="store_true", help="KIS 관심종목 그룹 목록 조회")
    mode.add_argument("--sync", action="store_true", help="관심종목을 동기화하고 Watch Universe 생성")
    mode.add_argument("--show", action="store_true", help="저장된 Watch Universe 표시")
    parser.add_argument("--group", default="", help="특정 관심그룹 코드만 동기화 (예: 001)")
    args = parser.parse_args()

    configure_runtime_environment(args.environment)
    corr = f"corr_interest_{uuid4().hex[:10]}"
    if args.groups:
        return _print_result(interest_groups_query(corr, args.environment))
    if args.sync:
        return _print_result(sync_interest_watchlist(corr, args.environment, group_code=args.group))
    return _print_result(current_watch_universe(corr))


if __name__ == "__main__":
    raise SystemExit(main())
