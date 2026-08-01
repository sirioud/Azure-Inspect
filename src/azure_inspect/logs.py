"""Fetch the Azure activity log via the Monitor REST API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ._http import azure_get
from .config import ARM_API_VERSION, AzureConfig
from .models import ActivityEvent

_MONITOR_URL = "https://management.azure.com"


def get_activity_log(
    cfg: AzureConfig,
    hours: int = 24,
) -> list[ActivityEvent]:
    """Return activity-log events from the past `hours` for the subscription.

    The OData ``$filter`` is URL-encoded so timestamps with special characters
    (``+``, ``:``) don't break the query.

    Raises:
        RuntimeError: on persistent non-2xx responses from the Monitor API.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    filter_expr = (
        f"eventTimestamp ge '{start.isoformat()}'"
        f" and eventTimestamp le '{end.isoformat()}'"
    )
    url = (
        f"{_MONITOR_URL}/subscriptions/{cfg.subscription_id}"
        f"/providers/Microsoft.Insights/eventLogs?api-version={ARM_API_VERSION}"
        f"&$filter={quote(filter_expr)}"
    )
    items = azure_get(cfg, url)
    return [ActivityEvent.from_api(item) for item in items]
