from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="azure-inspect",
        description="Inspect an Azure tenant: resources, logs, and costs.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("resources", help="List resources (resource groups)")
    p_logs = sub.add_parser("logs", help="Query logs (Activity Log)")
    p_logs.add_argument("--last-hours", type=int, default=24, help="Look back N hours (default: 24)")
    p_logs.add_argument("--max", type=int, default=50, help="Max events to print (default: 50)")

    p_costs = sub.add_parser("costs", help="Query costs (Cost Management)")
    p_costs.add_argument("--year", type=int, default=None, help="Year (default: current UTC year)")
    p_costs.add_argument("--month", type=int, default=None, help="Month 1-12 (default: current UTC month)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.debug:
        print("[debug] args =", args)

    if args.command == "resources":
        from .config import load_config
        from .resources import list_resource_groups

        cfg = load_config()
        rgs = list_resource_groups(cfg.subscription_id)

        print(f"Found {len(rgs)} resource group(s):")
        for rg in rgs:
            print("-", rg.name)
        return 0

    if args.command == "logs":
        from .config import load_config
        from .logs import get_activity_log

        cfg = load_config()
        events = get_activity_log(cfg.subscription_id, hours=args.last_hours)
        
        print(f"Activity Log events (last {args.last_hours}h): {len(events)}")
        for e in events:
            ts=e.get("eventTimeStamp")
            op=(e.get("operationName")or {}).get("value")
            status=(e.get("status") or {}).get("value")
            caller= e.get("caller")
            rg=e.get("resourceGroupName")

            print(f"-ts | {status} | {op} | rg= {rg} | caller= {caller}")

        return 0
    
    if args.command == "costs":
        from .config import load_config
        from .costs import cost_by_resource_group

        cfg = load_config()
        data = cost_by_resource_group(cfg.subscription_id)

        cols = data.get("properties", {}).get("columns", [])
        rows = data.get("properties", {}).get("rows", [])

    # Figure out which column is RG and which is cost
        col_names = [c.get("name") for c in cols]
        rg_idx = col_names.index("ResourceGroup") if "ResourceGroup" in col_names else 0
        cost_idx = col_names.index("PreTaxCost") if "PreTaxCost" in col_names else 1

        print(f"Cost rows: {len(rows)} (grouped by ResourceGroup)")
        for row in rows:
            rg = row[rg_idx]
            cost = row[cost_idx]
            print(f"- {rg}: {cost}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
                              