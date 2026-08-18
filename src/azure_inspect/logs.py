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
    hours: int = 0,
) -> list[ActivityEvent]:
    """Return activity-log events from the past `hours` for the subscription.

    The activity log is a *tenant*-level resource, so it is queried at the
    tenant scope (``/providers/Microsoft.Insights/eventLogs``) with the
    subscription pinned via the OData ``resourceId`` filter. Subscription-
    scoped ``eventLogs`` returns ``InvalidResourceType``, which is why we use
    the tenant form.

    The OData ``$filter`` is URL-encoded so timestamps with special characters
    (``+``, ``:``) don't break the query.

    Raises:
        RuntimeError: on persistent non-2xx responses from the Monitor API.
            A 403 here means the service principal lacks Reader at tenant
            (directory) scope — the dashboard surfaces that as a friendly
            banner; granting the role in Entra ID resolves it.
    """
    if hours <= 0:
        hours = 24
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    base_filt = (
        f"eventTimestamp ge '{start.isoformat()}'"
        f" and eventTimestamp le '{end.isoformat()}'"
    )
    tenant_filt = f"{base_filt} and resourceId eq '/subscriptions/{cfg.subscription_id}'"
    encoded = quote(tenant_filt)

    url = (
        f"{_MONITOR_URL}/providers/Microsoft.Insights/eventLogs"
        f"?api-version={ACTIVITY_LOG_API_VERSION}"
        f"&$filter={encoded}"
    )
    items = azure_get(cfg, url, paginate=True)
    return [ActivityEvent.from_api(item) for item in items]
