"""Tests for the Azure-Inspect Flask dashboard (routes + error handling)."""
from unittest import mock

from azure_inspect.ui.app import create_app


def _client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health():
    r = _client().get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_index_renders():
    c = _client()
    r = c.get("/")
    assert r.status_code == 200
    assert b"Azure-Inspect" in r.data


def _rg(name="rg-a", loc="we", st="Succeeded"):
    return type("RG", (), {"name": name, "location": loc, "provisioning_state": st})()


def _cost(rg="rg-a", cost=12.3, cur="EUR"):
    return type("C", (), {"resource_group": rg, "cost": cost, "currency": cur})()


def _log():
    ts = type("D", (), {"isoformat": lambda self: "2026-01-01T00:00:00+00:00"})()
    return type("E", (), {"event_timestamp": ts, "operation": "write",
                          "resource_group": "rg-a", "caller": "u@x.com",
                          "status": "Succeeded"})()


def test_api_resources_ok():
    with mock.patch("azure_inspect.ui.app.list_resource_groups", return_value=[_rg()]):
        r = _client().get("/api/resources")
    assert r.status_code == 200
    assert r.get_json()[0]["name"] == "rg-a"


def test_api_costs_ok():
    with mock.patch("azure_inspect.ui.app.cost_by_resource_group", return_value=[_cost()]):
        r = _client().get("/api/costs")
    assert r.status_code == 200
    assert r.get_json()[0]["cost"] == 12.3


def test_api_logs_ok():
    with mock.patch("azure_inspect.ui.app.get_activity_log", return_value=[_log()]):
        r = _client().get("/api/logs")
    assert r.status_code == 200
    assert r.get_json()[0]["caller"] == "u@x.com"


def test_api_error_surfaces_500():
    with mock.patch("azure_inspect.ui.app.list_resource_groups", side_effect=RuntimeError("boom")):
        r = _client().get("/api/resources")
    assert r.status_code == 500
    assert "boom" in r.get_json()["error"]


def test_summary_endpoint():
    with mock.patch("azure_inspect.ui.app.list_resource_groups", return_value=[_rg()]), \
         mock.patch("azure_inspect.ui.app.cost_by_resource_group", return_value=[_cost()]), \
         mock.patch("azure_inspect.ui.app.get_activity_log", return_value=[_log()]):
        r = _client().get("/api/summary")
    assert r.status_code == 200
    s = r.get_json()
    assert s["resource_group_count"] == 1
    assert s["total_cost"] == 12.3
    assert s["activity_count"] == 1
