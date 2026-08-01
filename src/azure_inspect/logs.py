"""Fetch the Azure activity log via the Monitor REST API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .auth import get_access_token
from .config import ARM_API_VERSION, AzureConfig
from .models import ActivityEvent

_MONITOR_URL = "https://management.azure.com"


def get_activity_log(
    cfg: AzureConfig,
    hours: int = 24,
) -> list[ActivityEvent]:
    """Return activity-log events from the past `hours` for the subscription.

    Raises:
        RuntimeError: on non-2xx responses from the Monitor API.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    token = get_access_token(cfg)

    filter_expr = (
        f"eventTimestamp ge '{start.isoformat()}'"
        f" and eventTimestamp le '{end.isoformat()}'"
    )
    url = (
        f"{_MONITOR_URL}/subscriptions/{cfg.subscription_id}"
        f"/providers/Microsoft.Insights/eventLogs?api-version={ARM_API_VERSION}"
        f"&$filter={filter_expr}"
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"get_activity_log failed: {resp.status_code} {resp.text}"
        )

    payload: dict[str, Any] = resp.json()
    return [ActivityEvent.from_api(item) for item in payload.get("value", [])]
