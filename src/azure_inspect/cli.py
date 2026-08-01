"""Command-line interface for Azure-Inspect."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from .config import load_config
from .costs import cost_by_resource_group
from .logs import get_activity_log
from .resources import list_resource_groups


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="azure-inspect",
        description="Inspect Azure resources, cost and activity log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("resources", help="List resource groups")

    p_cost = sub.add_parser("cost", help="Show cost per resource group")
    p_cost.add_argument("--days", type=int, default=30, help="Trailing window in days")

    p_logs = sub.add_parser("activity", help="Show recent activity-log events")
    p_logs.add_argument("--hours", type=int, default=24, help="Trailing window in hours")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    try:
        cfg = load_config()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "resources":
        for rg in list_resource_groups(cfg):
            print(f"{rg.name}\t{rg.location}\t{rg.provisioning_state}")

    elif args.command == "cost":
        for c in cost_by_resource_group(cfg):
            print(f"{c.resource_group}\t{c.cost:.2f} {c.currency}")

    elif args.command == "activity":
        for e in get_activity_log(cfg, hours=args.hours):
            ts = e.event_timestamp.strftime("%Y-%m-%d %H:%M")
            print(f"{ts}\t{e.operation}\t{e.resource_group}\t{e.caller}\t{e.status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
