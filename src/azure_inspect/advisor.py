"""Azure Advisor recommendations via the REST API.

Advisor surfaces cost/performance/reliability/operational-excellence
recommendations. We normalise them for a dashboard panel.
"""
from __future__ import annotations

from ._http import azure_get
from .config import AzureConfig

_ADVISOR_URL = (
    "https://management.azure.com/subscriptions/{sub}"
    "/providers/Microsoft.Advisor/recommendations"
    "?api-version=2023-01-01&$expand=properties"
)


def get_recommendations(cfg: AzureConfig) -> list[dict]:
    """Return normalised Advisor recommendations.

    Each item: {category, impact, short_description, resource, risk,
    potential_benefit, last_updated}
    """
    url = _ADVISOR_URL.format(sub=cfg.subscription_id)
    items = azure_get(cfg, url, paginate=True)
    out = []
    for it in items:
        p = it.get("properties", {})
        out.append({
            "category": p.get("category", "Unknown"),
            "impact": p.get("impact", "Unknown"),
            "short_description": (p.get("shortDescription") or {}).get("problem", ""),
            "resource": p.get("impactedValue", ""),
            "risk": p.get("risk", ""),
            "potential_benefit": p.get("potentialBenefits", ""),
            "last_updated": p.get("lastUpdated", ""),
        })
    # High impact first
    rank = {"High": 0, "Medium": 1, "Low": 2}
    out.sort(key=lambda x: rank.get(x["impact"], 3))
    return out
