from typing import List
import requests
from datetime import datetime, timedelta

from .config import load_config
from .auth import get_access_token


def get_activity_log(subscription_id: str, hours: int = 24) -> List[dict]:

    config = load_config()
    token = get_access_token(config)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/microsoft.insights/eventtypes/management/values"

    params = {
        "api-version": "2015-04-01",
        "$filter": f"eventTimestamp ge '{start_time.isoformat()}Z' and eventTimestamp le '{end_time.isoformat()}Z'"
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()

    return r.json().get("value", [])