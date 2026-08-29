"""Resource inventory via Azure Resource Graph (POST query API).

Resource Graph is the fastest way to get a subscription-wide inventory
(resource counts by type/location, tag coverage) without paging every
ARM list endpoint. It requires a POST with a KQL ``query`` body.
"""
from __future__ import annotations

from ._http import azure_post_json
from .config import AzureConfig

_RG_URL = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2024-04-01"


def _query(cfg: AzureConfig, kql: str) -> list[dict]:
    """Run a Resource Graph query, return rows normalised to list[dict]."""
    body = {"subscriptions": [cfg.subscription_id], "query": kql}
    resp = azure_post_json(cfg, _RG_URL, body)
    rows = []
    if "tables" in resp:
        rows = resp["tables"][0].get("rows", [])
    elif "data" in resp:
        rows = resp["data"] if isinstance(resp["data"], list) else []
    # Normalise: Resource Graph returns either list-of-lists (tables shape)
    # or list-of-dicts (legacy/data shape). Unify to dicts.
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
        elif isinstance(r, (list, tuple)):
            # columns unknown here; best-effort map by position
            out.append({"type": r[0], "count": r[1]} if len(r) >= 2 else {"value": r[0]})
    return out


def resource_inventory(cfg: AzureConfig) -> dict:
    """Subscription-wide inventory summary for dashboard charts.

    Returns a dict with:
      - total_resources, total_rgs
      - by_type: [{type, count}] (resource types, desc)
      - by_location: [{location, count}]
      - tagged_rgs, untagged_rgs (governance signal)
    """
    def _cell(row, *keys, pos=0):
        for k in keys:
            if isinstance(row, dict) and k in row:
                return row[k]
        if isinstance(row, (list, tuple)) and len(row) > pos:
            return row[pos]
        return 0

    by_type = [
        {"type": _cell(r, "type", "ResourceType", pos=0), "count": _cell(r, "count", "count_", pos=1)}
        for r in _query(cfg, "Resources | summarize count() by type | order by count_ desc")
    ]
    by_location = [
        {"location": _cell(r, "location", pos=0) or "unknown", "count": _cell(r, "count", "count_", pos=1)}
        for r in _query(cfg, "Resources | summarize count() by location | order by count_ desc")
    ]
    total = _query(cfg, "Resources | count")
    total_resources = int(_cell(total[0], "count", "Count", pos=0)) if total else sum(t["count"] for t in by_type)

    rg_rows = _query(
        cfg,
        "resourcecontainers | where type == 'resourcegroup' "
        "| extend hasEnv = iff(isnotnull(tags['env']), 1, 0) "
        "| summarize total = count(), tagged = sum(hasEnv)",
    )
    # Resource Graph tag query can be flaky across tenants; fall back to the
    # ARM resource-group list (which carries tags) for an accurate count.
    total_rgs = int(_cell(rg_rows[0], "total", "Total", pos=0)) if rg_rows else 0
    tagged_rgs = int(_cell(rg_rows[0], "tagged", "Tagged", pos=1)) if rg_rows else 0
    if total_rgs == 0:
        from .resources import list_resource_groups
        try:
            rgs = list_resource_groups(cfg)
            total_rgs = len(rgs)
            tagged_rgs = sum(1 for rg in rgs if rg.tags and "env" in rg.tags)
        except Exception:
            total_rgs = total_rgs or 0

    return {
        "total_resources": total_resources,
        "total_rgs": total_rgs,
        "tagged_rgs": tagged_rgs,
        "untagged_rgs": total_rgs - tagged_rgs,
        "by_type": by_type,
        "by_location": by_location,
    }
