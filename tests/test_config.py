"""Tests for azure_inspect.config."""
import importlib

import pytest

from azure_inspect import config as config_mod


def test_load_config_missing_raises(monkeypatch, tmp_path):
    # Point load_config at an empty .env so dotenv cannot populate anything,
    # and clear any values already present in the process environment.
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    for var in config_mod._REQUIRED:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):
        config_mod.load_config(env_path=empty_env)


def test_load_config_reads_env(monkeypatch):
    for var in config_mod._REQUIRED:
        monkeypatch.setenv(var, "test-" + var)
    cfg = config_mod.load_config(env_path=None)
    assert cfg.tenant_id == "test-AZURE_TENANT_ID"
    assert cfg.authority.endswith("/test-AZURE_TENANT_ID")
    assert cfg.arm_scope == ["https://management.azure.com/.default"]


def test_azure_config_frozen():
    cfg = config_mod.AzureConfig("t", "c", "s", "sub")
    with pytest.raises(Exception):
        cfg.tenant_id = "x"  # type: ignore[misc]
