"""Shared HTTP helpers: cached token acquisition, retry/backoff, pagination.

Centralises the Azure REST plumbing so the feature modules stay thin and every
call gets consistent error handling, retries on transient failures, and token
caching (MSAL already caches internally, but we surface a stable helper).
"""
from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from .auth import get_access_token
from .config import AzureConfig

# Retry on transient errors (429 rate-limit, 500/502/503/504).
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds, doubled each attempt


def _session() -> requests.Session:
    """A session with retry/backoff for transient Azure errors."""
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=0)  # we do our own retry loop below
    s.mount("https://", adapter)
    return s


def azure_get(
    cfg: AzureConfig,
    url: str,
    *,
    params: dict[str, str] | None = None,
    paginate: bool = False,
) -> list[dict[str, Any]]:
    """GET from an Azure REST endpoint with auth, retry and optional pagination.

    Args:
        cfg: Azure connection config.
        url: Fully-qualified URL (without auth header).
        params: Optional query-string params (URL-encoded for you).
        paginate: If True, follow `nextLink` and collect all `value` entries.

    Returns:
        A list of the `value` items (concatenated across pages when paginating).

    Raises:
        RuntimeError: on persistent non-2xx responses.
    """
    token = get_access_token(cfg)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    items: list[dict[str, Any]] = []
    session = _session()
    next_url: str | None = url

    while next_url:
        attempt = 0
        while True:
            resp = session.get(
                next_url, headers=headers, params=params if next_url == url else None,
                timeout=30,
            )
            if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                attempt += 1
                time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            break

        if resp.status_code != 200:
            raise RuntimeError(f"GET {next_url} failed: {resp.status_code} {resp.text}")

        payload = resp.json()
        items.extend(payload.get("value", []))
        next_url = payload.get("nextLink") if paginate else None
        params = None  # nextLink already carries full query

    return items


def azure_post_json(
    cfg: AzureConfig,
    url: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """POST JSON to an Azure REST endpoint with auth and retry/backoff.

    Raises:
        RuntimeError: on persistent non-2xx responses.
    """
    token = get_access_token(cfg)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    session = _session()
    attempt = 0
    while True:
        resp = session.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
            attempt += 1
            time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
            continue
        break

    if resp.status_code != 200:
        raise RuntimeError(f"POST {url} failed: {resp.status_code} {resp.text}")
    return resp.json()
