"""List Azure resource groups via the Resource Manager REST API."""
from __future__ import annotations

from ._http import azure_get
from .config import ARM_API_VERSION, AzureConfig
from .models import ResourceGroup

_ARM_URL = "https://management.azure.com"


def list_resource_groups(
    cfg: AzureConfig,
    top: int = 100,
) -> list[ResourceGroup]:
    """Return all resource groups in the configured subscription.

    Follows Azure's ``nextLink`` pagination automatically, so this returns the
    complete list even for subscriptions with more than ``top`` groups.

    Raises:
        RuntimeError: on persistent non-2xx responses from the ARM API.
    """
    url = (
        f"{_ARM_URL}/subscriptions/{cfg.subscription_id}"
        f"/resourcegroups?api-version={ARM_API_VERSION}&$top={top}"
    )
    items = azure_get(cfg, url, paginate=True)
    return [ResourceGroup.from_api(item) for item in items]
