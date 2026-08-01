"""Tests for azure_inspect.models parsing from Azure API payloads."""
from datetime import datetime, timezone

from azure_inspect.models import ActivityEvent, CostSummary, ResourceGroup


def test_resource_group_from_api():
    payload = {
        "name": "rg-prod",
        "location": "westeurope",
        "properties": {"provisioningState": "Succeeded"},
        "tags": {"env": "prod"},
    }
    rg = ResourceGroup.from_api(payload)
    assert rg.name == "rg-prod"
    assert rg.location == "westeurope"
    assert rg.provisioning_state == "Succeeded"
    assert rg.tags == {"env": "prod"}


def test_cost_summary_dataclass():
    c = CostSummary(resource_group="rg-x", currency="EUR", cost=12.5)
    assert c.cost == 12.5


def test_activity_event_from_api():
    payload = {
        "eventTimestamp": "2026-07-04T12:00:00Z",
        "properties": {
            "operationName": "Microsoft.Resources/ deployments/write",
            "resourceGroupName": "rg-x",
            "caller": "user@contoso.com",
            "status": "Succeeded",
        },
    }
    ev = ActivityEvent.from_api(payload)
    assert ev.operation.endswith("write")
    assert ev.resource_group == "rg-x"
    assert ev.caller == "user@contoso.com"
    assert ev.event_timestamp == datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
