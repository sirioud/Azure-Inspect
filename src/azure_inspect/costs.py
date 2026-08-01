"""Query Azure Cost Management for per-resource-group spend."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ._http import azure_post_json
from .config import AzureConfig
from .models import CostSummary

_COST_URL = "https://management.azure.com"
_COST_API_VERSION = "2023-03-01"


def cost_by_resource_group(
    cfg: AzureConfig,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[CostSummary]:
    """Return cost aggregated per resource group for a date window.

    Defaults to the trailing 30 days when no window is supplied.

    Raises:
        RuntimeError: on persistent non-2xx responses from the Cost Management API.
    """
    if to_date is None:
        to_date = date.today()
    if from_date is None:
        from_date = to_date - timedelta(days=30)

    scope = f"/subscriptions/{cfg.subscription_id}"
    url = (
        f"{_COST_URL}{scope}/providers/Microsoft.CostManagement"
        f"/query?api-version={_COST_API_VERSION}"
    )
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        },
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceGroup"}],
        },
    }
    payload = azure_post_json(cfg, url, body)
    return _parse_cost_response(payload)


def _parse_cost_response(payload: dict[str, Any]) -> list[CostSummary]:
    props = payload.get("properties", {})
    rows = props.get("rows", [])
    columns = [c.get("name") for c in props.get("columns", [])]
    cost_idx = columns.index("Cost") if "Cost" in columns else None
    rg_idx = columns.index("ResourceGroup") if "ResourceGroup" in columns else None
    currency_idx = columns.index("Currency") if "Currency" in columns else None

    summaries: list[CostSummary] = []
    for row in rows:
        if cost_idx is None:
            continue
        summaries.append(
            CostSummary(
                resource_group=row[rg_idx] if rg_idx is not None else "",
                currency=row[currency_idx] if currency_idx is not None else "",
                cost=float(row[cost_idx]),
            )
        )
    return summaries
