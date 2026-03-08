from __future__ import annotations
import msal
from .config import AzureConfig

def get_access_token(cfg: AzureConfig) -> str:
    authority = f"https://login.microsoftonline.com/{cfg.tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=cfg.client_id,
        client_credential=cfg.client_secret,
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=["https://management.azure.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Token error: {result.get('error')} - {result.get('error_description')}")
    return result["access_token"]
