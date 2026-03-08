from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AzureConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    subscription_id: str


def load_config() -> AzureConfig:
    # Load .env located at the PROJECT ROOT (two levels up from this file):
    # src/azure_inspect/config.py -> project root is parents[2]
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"

    # Fallback: if no .env, try example names (dev convenience)
    if env_path.exists():
        load_dotenv(env_path)
    else:
        for candidate in (project_root / ".env.example", project_root / "env.example"):
            if candidate.exists():
                load_dotenv(candidate)
                break

    def req(k: str) -> str:
        v = os.getenv(k, "").strip()
        if not v:
            raise ValueError(f"Missing env var: {k} (expected in {env_path})")
        return v

    return AzureConfig(
        tenant_id=req("AZURE_TENANT_ID"),
        client_id=req("AZURE_CLIENT_ID"),
        client_secret=req("AZURE_CLIENT_SECRET"),
        subscription_id=req("AZURE_SUBSCRIPTION_ID"),
    )
