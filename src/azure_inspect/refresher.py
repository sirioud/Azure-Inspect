"""refresher.py — background refresh loop for Azure-Inspect.

The dashboard serves data from the SQLite cache (see cache.py). This module
runs a daemon thread that periodically re-fetches every dataset from Azure
and writes it into the cache, so:

* the dashboard is instant (served from cache, no live wait),
* a transient Azure outage degrades to stale data, not a blank page,
* we stay well under Azure rate limits (one pull per dataset per interval).

It is deliberately crash-tolerant: any single fetch error is logged and the
loop continues; the cache keeps the last good value.

Start it with ``start_refresher(cache)`` from the dashboard entrypoint.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from .cache import DataCache
from .config import load_config
from .costs import cost_by_resource_group
from .logs import get_activity_log
from .resources import list_resource_groups

log = logging.getLogger("azure_inspect.refresher")

# Datasets the refresher keeps warm, with the callable that produces them.
# Each returns a JSON-serialisable value (cached via DataCache.set).
def _build_jobs(cfg):
    def summary():
        rgs = list_resource_groups(cfg)
        costs = cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=30))
        total = sum(c.cost for c in costs)
        currency = costs[0].currency if costs else ""
        try:
            logs = get_activity_log(cfg, hours=24)
        except Exception:
            logs = []
        return {
            "subscription_id": cfg.subscription_id,
            "resource_group_count": len(rgs),
            "total_cost": round(total, 2),
            "currency": currency,
            "activity_count": len(logs),
        }

    return {
        "summary": summary,
        "resources": lambda: [
            {"name": rg.name, "location": rg.location,
             "provisioning_state": rg.provisioning_state}
            for rg in list_resource_groups(cfg)
        ],
        "costs_30": lambda: [
            {"resource_group": c.resource_group, "cost": c.cost, "currency": c.currency}
            for c in cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=30))
        ],
        "costs_7": lambda: [
            {"resource_group": c.resource_group, "cost": c.cost, "currency": c.currency}
            for c in cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=7))
        ],
        "costs_90": lambda: [
            {"resource_group": c.resource_group, "cost": c.cost, "currency": c.currency}
            for c in cost_by_resource_group(cfg, from_date=date.today() - timedelta(days=90))
        ],
        "logs": lambda: [
            {"event_timestamp": e.event_timestamp.isoformat(), "operation": e.operation,
             "resource_group": e.resource_group, "caller": e.caller, "status": e.status}
            for e in get_activity_log(cfg, hours=24)
        ],
    }


def _refresh_once(cache: DataCache, cfg) -> dict[str, str]:
    """Refresh every dataset once. Returns {key: 'ok'|'error'}."""
    results: dict[str, str] = {}
    jobs = _build_jobs(cfg)
    names = list(jobs.keys())
    for i, key in enumerate(names):
        try:
            cache.set(key, jobs[key]())
            results[key] = "ok"
        except Exception as exc:  # keep the last good value; mark this attempt
            log.warning("refresh failed for %s: %s", key, exc)
            results[key] = "error"
        # Stagger between jobs so we don't burst the Cost Management API
        # (concurrent ActualCost queries can hit 429 throttling). Skip the
        # pause after the last job.
        if i < len(names) - 1:
            time.sleep(1.5)
    return results


def start_refresher(
    cache: DataCache,
    interval_min: int | None = None,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Start the background refresh loop as a daemon thread.

    Args:
        cache: the shared DataCache.
        interval_min: override for the refresh interval (env REFRESH_INTERVAL_MIN
            is the default source, fallback 15).
        stop_event: optional Event to stop the loop (used in tests).

    Returns the started Thread (already .start()'d).
    """
    interval = interval_min or int(os.getenv("REFRESH_INTERVAL_MIN", "15"))
    stop_event = stop_event or threading.Event()

    def _run():
        try:
            cfg = load_config()
        except Exception as exc:
            log.error("refresher cannot load config, not starting: %s", exc)
            return
        log.info("refresher started (interval=%dm)", interval)
        # Initial fill so the cache is warm before the first user request.
        _refresh_once(cache, cfg)
        while not stop_event.is_set():
            if stop_event.wait(interval * 60):
                break
            try:
                _refresh_once(cache, cfg)
            except Exception as exc:  # never let the loop die
                log.error("refresher loop error: %s", exc)

    t = threading.Thread(target=_run, name="azure-inspect-refresher", daemon=True)
    t.start()
    return t
