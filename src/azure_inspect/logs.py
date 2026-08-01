"""Fetch the Azure activity log via the Monitor REST API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ._http import azure_get
from .config import ARM_API_VERSION, ACTIVITY_LOG_API_VERSION, AzureConfig
from .models import ActivityEvent

_MONITOR_URL = "https://management.azure.com"


def get_activity_log(
    cfg: AzureConfig,
    hours: int = 24,
) -> list[ActivityEvent]:
    """Return activity-log events from the past `hours` for the subscription.

    Uses the tenant/root-level activity-log endpoint
    (``/providers/Microsoft.Insights/eventLogs``) with ``api-version=2017-03-01-preview``,
    scoping the OData ``$filter`` to this subscription via ``resourceId``. The
    subscription-scoped path is deprecated and returns InvalidResourceType.

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
        f" and resourceId eq '/subscriptions/{cfg.subscription_id}'"
    )
    url = (
        f"{_MONITOR_URL}/providers/Microsoft.Insights/eventLogs"
        f"?api-version={ACTIVITY_LOG_API_VERSION}"
        f"&$filter={quote(filter_expr)}"
    )
    items = azure_get(cfg, url)
    return [ActivityEvent.from_api(item) for item in items]
