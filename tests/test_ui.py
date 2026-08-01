"""Tests for the Azure-Inspect Flask dashboard (routes + error handling)."""
from datetime import date, timedelta
from unittest import mock

from azure_inspect.ui.app import create_app


def _stub_cfg():
    cfg = mock.Mock()
    cfg.subscription_id = "sub-123"
    return cfg


def _client(config_provider=None):
    if config_provider is None:
        config_provider = _stub_cfg
    app = create_app(config_provider=config_provider, auth=False)
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


# --- New: dashboard hardening & testability ---------------------------------


def test_not_configured_returns_503_with_code():
    """Without a resolvable config the app must report not_configured, not a raw 500."""
    import os
    # A provider that mimics load_config() failing when creds are absent.
    def raising():
        raise RuntimeError("Missing required environment variable(s)")
    app = create_app(config_provider=raising, auth=False)
    app.config["TESTING"] = True
    with mock.patch.dict(os.environ, {}, clear=True):
        r = app.test_client().get("/api/summary")
    assert r.status_code == 503
    body = r.get_json()
    assert body["code"] == "not_configured"
    assert "credentials" in body["error"].lower()


def test_config_provider_injection_supplies_cfg():
    """Injecting a config_provider should let endpoints resolve without env."""
    cfg = mock.Mock()
    cfg.subscription_id = "sub-123"
    with mock.patch("azure_inspect.ui.app.list_resource_groups", return_value=[_rg()]), \
         mock.patch("azure_inspect.ui.app.cost_by_resource_group", return_value=[_cost()]), \
         mock.patch("azure_inspect.ui.app.get_activity_log", return_value=[_log()]):
        r = _client(config_provider=lambda: cfg).get("/api/summary")
    assert r.status_code == 200
    assert r.get_json()["subscription_id"] == "sub-123"


def test_costs_days_query_forwards_window():
    """?days=90 must request a 90-day trailing window from cost_by_resource_group."""
    captured = {}

    def fake_cost(cfg, from_date=None, to_date=None):
        captured["from_date"] = from_date
        return [_cost()]

    with mock.patch("azure_inspect.ui.app.cost_by_resource_group", side_effect=fake_cost):
        r = _client().get("/api/costs?days=90")
    assert r.status_code == 200
    assert captured["from_date"] == date.today() - timedelta(days=90)


def test_costs_invalid_days_falls_back_to_30():
    """A non-allowed ?days value must clamp to the 30-day default."""
    captured = {}

    def fake_cost(cfg, from_date=None, to_date=None):
        captured["from_date"] = from_date
        return [_cost()]

    with mock.patch("azure_inspect.ui.app.cost_by_resource_group", side_effect=fake_cost):
        r = _client().get("/api/costs?days=999")
    assert r.status_code == 200
    assert captured["from_date"] == date.today() - timedelta(days=30)


def test_auth_gate_disabled_when_password_unset():
    """With no DASHBOARD_PASSWORD and auth=True default, but env-driven, _client
    forces auth=False — ensure index is reachable without a session."""
    r = _client().get("/")
    assert r.status_code == 200


def test_auth_gate_enabled_with_password():
    """When a dashboard password is set, unauthenticated access redirects to login."""
    import azure_inspect.ui.app as m
    app = m.create_app(config_provider=_stub_cfg, auth=True)
    app.config["TESTING"] = True
    c = app.test_client()
    # / and an API must both redirect to /login when unauthenticated
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers.get("Location", "")
    r = c.get("/api/resources", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers.get("Location", "")


def test_auth_gate_login_success_and_failure():
    """Wrong password is rejected; correct password grants access."""
    import azure_inspect.ui.app as m
    app = m.create_app(config_provider=_stub_cfg, auth=True)
    app.config["TESTING"] = True
    c = app.test_client()
    pw = app.secret_key  # not the pw; we need the generated throwaway pw — read env
    # The throwaway pw is set in required_pw but not exposed; log in via the
    # app's own password by capturing it through monkeypatch on the closure.
    # Simpler: set the env and rebuild.
    import os
    os.environ["DASHBOARD_PASSWORD"] = "correct-horse-battery-staple"
    app2 = m.create_app(config_provider=_stub_cfg, auth=True)
    c2 = app2.test_client()
    # wrong password
    r = c2.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 200 and b"Incorrect" in r.data
    # correct password
    r = c2.post("/login", data={"password": "correct-horse-battery-staple"}, follow_redirects=False)
    assert r.status_code == 302 and "/" in r.headers.get("Location", "")
    # now authenticated
    r = c2.get("/")
    assert r.status_code == 200
    del os.environ["DASHBOARD_PASSWORD"]
