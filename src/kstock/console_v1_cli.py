from __future__ import annotations

import argparse
import traceback

from .cli_support import JsonlEmitter, diagnostic, force_utf8_stdio
from .demo_services import (
    account_query,
    audit_health,
    audit_recent,
    audit_trace,
    buying_power_query,
    cancel_open_orders,
    close_gate,
    dart_collect,
    dart_replay,
    full_check,
    gate_status,
    halt_trading,
    inject_audit_failure,
    inject_quote_mode,
    inject_reconciliation_mode,
    kill_status,
    open_gate,
    order_submit_out_of_scope,
    quick_check,
    quote_query,
    reconcile,
    repair_demo,
    resume_trading,
    seed_open_order,
    seed_unknown_order,
    start_console_session,
)
from .models import ResultStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="K-Stock Console V1 demo CLI")
    parser.add_argument("group")
    parser.add_argument("action")
    parser.add_argument("--environment", type=str.upper, choices=["PAPER", "LIVE"], default="PAPER")
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--output", default="jsonl", choices=["jsonl"])
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--price", type=int, default=0)
    parser.add_argument("--enabled", choices=["true", "false"], default="true")
    parser.add_argument("--mode", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--target-correlation-id", default="")
    return parser


def dispatch(args):
    key = (args.group, args.action)
    corr = args.correlation_id

    if key == ("startup", "session-init"):
        return start_console_session(corr, args.environment)
    if key == ("startup", "quick-check"):
        return quick_check(corr, args.environment)
    if key == ("startup", "full-check"):
        return full_check(corr, args.environment)
    if key == ("gate", "status"):
        return gate_status(corr)
    if key == ("gate", "open"):
        return open_gate(corr, args.confirmation)
    if key == ("gate", "close"):
        return close_gate(corr, args.reason)

    if key == ("account", "query"):
        return account_query(corr, args.environment)
    if key == ("quote", "query"):
        return quote_query(corr, args.symbol)
    if key == ("account", "buying-power"):
        return buying_power_query(corr, args.symbol, args.price, args.environment)
    if key == ("dart", "collect"):
        return dart_collect(corr)
    if key == ("dart", "replay"):
        return dart_replay(corr)

    if key == ("reconcile", "run"):
        return reconcile(corr)
    if key == ("reconcile", "repair-demo"):
        return repair_demo(corr, args.confirmation)

    if key == ("orders", "cancel-open"):
        return cancel_open_orders(corr, args.confirmation)
    if key == ("order", "submit"):
        return order_submit_out_of_scope(corr)

    if key == ("kill", "status"):
        return kill_status(corr)
    if key == ("ops", "halt"):
        return halt_trading(corr, args.reason)
    if key == ("ops", "resume"):
        return resume_trading(corr, args.confirmation, args.reason)

    if key == ("audit", "health"):
        return audit_health(corr)
    if key == ("audit", "recent"):
        return audit_recent(corr, args.limit)
    if key == ("audit", "trace"):
        return audit_trace(corr, args.target_correlation_id)

    if key == ("demo", "reconciliation-mode"):
        return inject_reconciliation_mode(corr, args.mode)
    if key == ("demo", "quote-mode"):
        return inject_quote_mode(corr, args.mode)
    if key == ("demo", "seed-open-order"):
        return seed_open_order(corr)
    if key == ("demo", "seed-unknown-order"):
        return seed_unknown_order(corr)
    if key == ("demo", "audit-failure"):
        return inject_audit_failure(corr, args.enabled == "true")

    raise ValueError(f"알 수 없는 명령: {args.group} {args.action}")


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    emitter = JsonlEmitter(args.correlation_id)
    emitter.progress("dispatch", f"{args.group} {args.action} 실행 중")
    try:
        result = dispatch(args)
        return emitter.result(
            result.status,
            result.code,
            result.message,
            result.payload,
            result.next_action,
        )
    except Exception as exc:
        diagnostic(traceback.format_exc())
        return emitter.result(
            ResultStatus.ERROR,
            "UNHANDLED_EXCEPTION",
            str(exc),
            {},
            "stderr 진단 로그를 확인하십시오.",
        )


if __name__ == "__main__":
    raise SystemExit(main())
