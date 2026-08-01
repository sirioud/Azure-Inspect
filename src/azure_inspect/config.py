"""Configuration loading for Azure-Inspect.

Credentials are read from environment variables (typically via a local .env
file that is NEVER committed to the repository). See .env.example.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Azure Resource Manager REST API version used across calls.
ARM_API_VERSION = "2024-03-01"

# Where load_config looks for the .env file when not already in the environment.
DEFAULT_ENV_PATH = Path.cwd() / ".env"


@dataclass(frozen=True)
class AzureConfig:
    """Connection details for a service principal (client-credentials auth)."""

    tenant_id: str
    client_id: str
    client_secret: str
    subscription_id: str

    @property
    def authority(self) -> str:
        """MSAL authority endpoint for this tenant."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def arm_scope(self) -> list[str]:
        """Resource scope requested from MSAL for ARM access."""
        return ["https://management.azure.com/.default"]


_REQUIRED = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_SUBSCRIPTION_ID")


def load_config(env_path: Path | None = None) -> AzureConfig:
    """Load configuration from the environment, optionally loading a .env file first.

    Raises:
        RuntimeError: if any required environment variable is missing.
    """
    load_dotenv(env_path or DEFAULT_ENV_PATH)

    missing = [name for name in _REQUIRED if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    return AzureConfig(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
        subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
    )
