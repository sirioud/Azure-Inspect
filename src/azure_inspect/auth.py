"""Azure authentication via MSAL (service principal / client-credentials flow)."""
from __future__ import annotations

import msal

from .config import AzureConfig


def get_access_token(cfg: AzureConfig) -> str:
    """Acquire an ARM access token for the service principal.

    Raises:
        RuntimeError: if MSAL fails to return an access token (e.g. bad
            credentials, expired secret, or insufficient permissions).
    """
    app = msal.ConfidentialClientApplication(
        client_id=cfg.client_id,
        authority=cfg.authority,
        client_credential=cfg.client_secret,
    )
    result = app.acquire_token_for_client(scopes=cfg.arm_scope)
    if "access_token" not in result:
        description = result.get("error_description", "no error description")
        raise RuntimeError(f"Failed to acquire Azure access token: {description}")
    return result["access_token"]
