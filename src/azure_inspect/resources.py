from typing import List
import requests

from .models import ResourceGroup
from .config import load_config
from .auth import get_access_token


def list_resource_groups(subscription_id: str, top: int = 50) -> List[ResourceGroup]:
    config = load_config()
    token = get_access_token(config)

    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups"

    params = {
        "api-version": "2021-04-01"
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()

    items = r.json().get("value", [])[:top]

    return [
        ResourceGroup(
            name=rg["name"],
            location=rg["location"],
            provisioning_state=rg["properties"].get("provisioningState"),
            tags=rg.get("tags"),
        )
        for rg in items
    ]