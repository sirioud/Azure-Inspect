"""Tests for the Azure REST modules using a mocked token + HTTP layer."""
from unittest import mock

import pytest

from azure_inspect import costs, logs, resources
from azure_inspect.auth import get_access_token
from azure_inspect.config import AzureConfig


@pytest.fixture
def cfg():
    return AzureConfig(
        tenant_id="t", client_id="c", client_secret="s", subscription_id="sub-123"
    )


def test_get_access_token_returns_token():
    fake_app = mock.Mock()
    fake_app.acquire_token_for_client.return_value = {"access_token": "tok-abc"}
    with mock.patch("azure_inspect.auth.msal.ConfidentialClientApplication", return_value=fake_app):
        assert get_access_token(cfg := AzureConfig("t", "c", "s", "sub")) == "tok-abc"


def test_get_access_token_raises_on_failure():
    fake_app = mock.Mock()
    fake_app.acquire_token_for_client.return_value = {"error": "invalid_grant",
                                                      "error_description": "bad secret"}
    with mock.patch("azure_inspect.auth.msal.ConfidentialClientApplication", return_value=fake_app):
        with pytest.raises(RuntimeError):
            get_access_token(AzureConfig("t", "c", "s", "sub"))


def test_list_resource_groups_parses_payload(cfg):
    arm = {
        "value": [
            {"name": "rg-a", "location": "westeurope",
             "properties": {"provisioningState": "Succeeded"}},
        ]
    }
    with mock.patch("azure_inspect.resources.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect.resources.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = arm
        rgs = resources.list_resource_groups(cfg)
    assert len(rgs) == 1
    assert rgs[0].name == "rg-a"


def test_list_resource_groups_http_error(cfg):
    with mock.patch("azure_inspect.resources.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect.resources.requests.get") as g:
        g.return_value.status_code = 403
        g.return_value.text = "Forbidden"
        with pytest.raises(RuntimeError):
            resources.list_resource_groups(cfg)


def test_cost_by_resource_group_parses_rows(cfg):
    resp = {
        "properties": {
            "columns": [
                {"name": "ResourceGroup"},
                {"name": "Cost"},
                {"name": "Currency"},
            ],
            "rows": [["rg-a", 12.34, "EUR"], ["rg-b", 5.0, "EUR"]],
        }
    }
    with mock.patch("azure_inspect.costs.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect.costs.requests.post") as p:
        p.return_value.status_code = 200
        p.return_value.json.return_value = resp
        result = costs.cost_by_resource_group(cfg)
    assert len(result) == 2
    assert result[0].resource_group == "rg-a"
    assert result[0].cost == 12.34


def test_get_activity_log_parses_payload(cfg):
    mon = {
        "value": [
            {"eventTimestamp": "2026-07-04T10:00:00Z",
             "properties": {"operationName": "write", "resourceGroupName": "rg-a",
                            "caller": "u@x.com", "status": "Succeeded"}},
        ]
    }
    with mock.patch("azure_inspect.logs.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect.logs.requests.get") as g:
        g.return_value.status_code = 200
        g.return_value.json.return_value = mon
        events = logs.get_activity_log(cfg, hours=24)
    assert len(events) == 1
    assert events[0].caller == "u@x.com"
