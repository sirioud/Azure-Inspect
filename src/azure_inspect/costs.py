from typing import List
import requests

from .config import load_config
from .auth import get_access_token


def cost_by_resource_group(subscription_id: str) -> List[dict]:

    config = load_config()
    token = get_access_token(config)

    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-03-01"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {
                "totalCost": {
                    "name": "Cost",
                    "function": "Sum"
                }
            },
            "grouping": [
                {
                    "type": "Dimension",
                    "name": "ResourceGroup"
                }
            ]
        }
    }

    r = requests.post(url, headers=headers, json=body)

    if not r.ok:
        print(r.text)
        r.raise_for_status()

    rows = r.json()["properties"]["rows"]

    return [
        {
            "name": row[0],
            "cost": row[1]
        }
        for row in rows
    ]