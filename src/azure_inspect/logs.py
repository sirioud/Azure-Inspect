"""Fetch the Azure activity log via the Monitor REST API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ._http import azure_get
from .config import ACTIVITY_LOG_API_VERSION, AzureConfig
from .models import ActivityEvent

_MONITOR_URL = "https://management.azure.com"


def _build_filter(start: datetime, end: datetime) -> str:
    return (
        f"eventTimestamp ge '{start.isoformat()}'"
        f" and eventTimestamp le '{end.isoformat()}'"
    )


def get_activity_log(
    cfg: AzureConfig,
    hours: int = 24,
) -> list[ActivityEvent]:
    """Return activity-log events from the past `hours` for the subscription.

    The activity log is a tenant-level resource, so we first try the
    subscription-scoped endpoint and fall back to the tenant-scoped endpoint
    (filtering by the subscription's ``resourceId``) when the subscription
    scope is rejected. Both use a stable api-version.

    The OData ``$filter`` is URL-encoded so timestamps with special characters
    (``+``, ``:``) don't break the query.

    Raises:
        RuntimeError: on persistent non-2xx responses from the Monitor API.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    filt = _build_filter(start, end)
    encoded = quote(filt)

    # Preferred: subscription-scoped query.
    sub_url = (
        f"{_MONITOR_URL}/subscriptions/{cfg.subscription_id}"
        f"/providers/Microsoft.Insights/eventlogs?api-version={ACTIVITY_LOG_API_VERSION}"
        f"&$filter={encoded}"
    )
    try:
        items = azure_get(cfg, sub_url)
        return [ActivityEvent.from_api(item) for item in items]
    except RuntimeError as sub_err:
        # Fall back to the tenant-scoped endpoint (activity logs live at tenant
        # scope); Azure redirects here and requires read at tenant/directory
        # scope for this to succeed.
        tenant_filt = f"{filt} and resourceId eq '/subscriptions/{cfg.subscription_id}'"
        tenant_url = (
            f"{_MONITOR_URL}/providers/Microsoft.Insights/eventlogs"
            f"?api-version={ACTIVITY_LOG_API_VERSION}&$filter={quote(tenant_filt)}"
        )
        try:
            items = azure_get(cfg, tenant_url)
            return [ActivityEvent.from_api(item) for item in items]
        except RuntimeError:
            # Surface the original subscription-scope error as the primary cause.
            raise sub_err
