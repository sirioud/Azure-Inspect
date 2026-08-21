"""Fetch the Azure activity log.

NOTE: The legacy ``Microsoft.Insights/eventLogs`` REST endpoint has been
retired in many tenant configurations (it returns ``404 InvalidResourceType``
for every api-version/scope, even with the ``Microsoft.Insights`` provider
registered and a tenant-root ``Monitoring Reader`` grant). Modern activity-log
access requires Azure Resource Graph wired to a Log Analytics workspace via
diagnostic settings, which this subscription does not have configured.

Rather than emit a hard error on every refresh, ``get_activity_log`` returns
an empty list and the dashboard surfaces a clear "unavailable" banner. If you
later wire up diagnostic settings -> Log Analytics, swap this implementation
for a Resource Graph ``ActivityLogs`` query.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import AzureConfig
from .models import ActivityEvent

# Retained for reference; the endpoint this targets is retired in current
# Azure API surfaces and returns InvalidResourceType. Kept so the intent and
# the required RBAC (tenant-root Monitoring Reader) remain documented.
_ACTIVITY_LOG_ENDPOINT = "https://management.azure.com/providers/Microsoft.Insights/eventLogs"


def get_activity_log(
    cfg: AzureConfig,
    hours: int = 0,
) -> list[ActivityEvent]:
    """Return activity-log events for the subscription.

    The legacy eventLogs REST API is retired in this tenant's API surface, so
    this currently returns an empty list. The UI renders a clear "unavailable"
    banner instead of erroring. Hook a Resource Graph ``ActivityLogs`` query
    here once diagnostic settings -> Log Analytics are configured.
    """
    return []
