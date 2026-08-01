"""List Azure resource groups via the Resource Manager REST API."""
from __future__ import annotations

from typing import Any

import requests

from .auth import get_access_token
from .config import ARM_API_VERSION, AzureConfig
from .models import ResourceGroup

_ARM_URL = "https://management.azure.com"


def list_resource_groups(
    cfg: AzureConfig,
    top: int = 100,
) -> list[ResourceGroup]:
    """Return resource groups in the configured subscription.

    Args:
        cfg: Azure connection config.
        top: maximum number of resource groups to return.

    Raises:
        RuntimeError: on non-2xx responses from the ARM API.
    """
    token = get_access_token(cfg)
    url = (
        f"{_ARM_URL}/subscriptions/{cfg.subscription_id}"
        f"/resourcegroups?api-version={ARM_API_VERSION}&$top={top}"
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"list_resource_groups failed: {resp.status_code} {resp.text}"
        )

    payload: dict[str, Any] = resp.json()
    return [ResourceGroup.from_api(item) for item in payload.get("value", [])]
