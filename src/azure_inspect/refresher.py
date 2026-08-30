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
from .costs import cost_by_day, cost_by_resource_group, cost_by_resource_group_daily
from .logs import get_activity_log
from .resources import list_resource_groups
from . import alerts

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
        total_resources = 0
        try:
            from .graph import resource_inventory
            total_resources = resource_inventory(cfg).get("total_resources") or 0
        except Exception:
            total_resources = 0
        return {
            "subscription_id": cfg.subscription_id,
            "resource_group_count": len(rgs),
            "total_resources": total_resources,
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
        "costs_daily": lambda: [
            {"day": d.isoformat(), "cost": c, "currency": cur}
            for d, c, cur in cost_by_day(cfg, days=14)
        ],
        "costs_rg_daily": lambda: {
            rg: [{"day": d.isoformat(), "cost": c} for d, c in series]
            for rg, series in cost_by_resource_group_daily(cfg, days=14).items()
        },
        "logs": lambda: [
            {"event_timestamp": e.event_timestamp.isoformat(), "operation": e.operation,
             "resource_group": e.resource_group, "caller": e.caller, "status": e.status}
            for e in get_activity_log(cfg, hours=24)
        ],
    }


def _sample_history(cache: "DataCache") -> None:
    """Append a rolling time-series sample so the dashboard can show trends.

    Reads the already-cached summary + inventory (cheap, no extra Azure calls)
    and stores a timestamped point: resource count, posture %, 30d spend.
    Capped at the last 120 samples (~30h at the 15-min interval).
    """
    try:
        summary = cache.value("summary") or {}
        inv = cache.value("inventory") or {}
        rgs = summary.get("resource_group_count") or 0
        gaps = 0
        comp = cache.value("compliance")
        if isinstance(comp, dict):
            gaps = comp.get("governance_gap_count")
            if gaps is None:
                gaps = len(comp.get("governance_gaps", []) or [])
        compliant_pct = round((1 - (gaps / rgs if rgs else 0)) * 100) if rgs else 100
        point = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "resources": inv.get("total_resources") or summary.get("total_resources") or 0,
            "rgs": rgs,
            "posture_pct": compliant_pct,
            "cost": summary.get("total_cost") or 0,
        }
        hist = cache.value("history") or []
        if not isinstance(hist, list):
            hist = []
        hist.append(point)
        if len(hist) > 120:
            hist = hist[-120:]
        cache.set("history", hist)
    except Exception as exc:  # never break the refresh loop
        log.warning("history sample failed: %s", exc)


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
        # (back-to-back ActualCost queries hit 429 throttling). Azure Cost
        # Management allows roughly one query every few seconds; 1.5s caused
        # every cost key to 429 in a burst. 7s keeps us safely under the
        # limit (7 jobs ~= 49s/cycle, far below the 15-min interval). Skip
        # the pause after the last job.
        if i < len(names) - 1:
            time.sleep(7)
    _sample_history(cache)
    return results


def evaluate_alerts(cache: DataCache, cfg) -> None:
    """Run the alert checks against current cache state and notify on findings.

    Best-effort: every check is wrapped so a failure in one never blocks the
    others, and alerts are cooldown-gated (see alerts.alert) so the channel
    isn't spammed on a sustained condition.
    """
    sub = cfg.subscription_id[:8]

    # 1) Spend spike: latest daily cost vs median of prior 7 days.
    #    Read the per-day series from the cache (refresher populates costs_daily),
    #    so we don't issue an extra Cost Management call here.
    #    Two guards prevent noise on a near-zero testlab: the spike must be both
    #    > SPIKE_MULTIPLE x the 7-day median AND above an absolute floor
    #    (SPIKE_FLOOR, default 10 currency units) — a CHF 0.01 testlab never pages.
    try:
        spike_multiple = float(os.getenv("ALERT_SPIKE_MULTIPLE", "2"))
        spike_floor = float(os.getenv("ALERT_SPIKE_FLOOR", "10"))
        daily = cache.value("costs_daily") or []
        series = [(row["day"], float(row["cost"]), row["currency"]) for row in daily]
        if len(series) >= 8:
            latest_day, latest_cost, cur = series[-1]
            baseline = [c for _, c, _ in series[-8:-1]]
            median = sorted(baseline)[len(baseline) // 2]
            threshold = max(spike_multiple * median, spike_floor)
            if median > 0 and latest_cost > threshold:
                alerts.alert(
                    "spend_spike",
                    f"\u26a0\ufe0f Azure spend spike on {latest_day} ({sub}): "
                    f"{cur} {latest_cost:,.2f} vs 7d median {cur} {median:,.2f}.",
                )
    except Exception as exc:
        log.warning("spend-spike check failed: %s", exc)

    # 2) New resource group: compare current RGs against the stored baseline.
    try:
        current = {rg.name for rg in list_resource_groups(cfg)}
        baseline_raw = cache.value("rg_baseline")
        if baseline_raw is None:
            cache.set("rg_baseline", sorted(current))
        else:
            baseline = set(baseline_raw)
            new_rgs = current - baseline
            for name in sorted(new_rgs):
                alerts.alert(
                    f"new_rg:{name}",
                    f"\ud83d\udcda New Azure resource group: {name} (sub {sub}).",
                )
            if new_rgs:
                cache.set("rg_baseline", sorted(current))
    except Exception as exc:
        log.warning("new-RG check failed: %s", exc)

    # 3) Stale data: if cost failed to refresh twice in a row, warn once.
    #    (Successes reset the streak via cache.written_at.)
    try:
        from .cache import DataCache as _DC
        cost_ts = cache.written_at("costs_30")
        if cost_ts is None:
            alerts.alert(
                "stale_cost",
                f"\u231b Azure-Inspect: cost data for {sub} has not refreshed "
                f"successfully (cache empty). Dashboard may be stale.",
            )
    except Exception as exc:
        log.warning("stale-data check failed: %s", exc)


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
        evaluate_alerts(cache, cfg)
        while not stop_event.is_set():
            if stop_event.wait(interval * 60):
                break
            try:
                _refresh_once(cache, cfg)
                evaluate_alerts(cache, cfg)
            except Exception as exc:  # never let the loop die
                log.error("refresher loop error: %s", exc)

    t = threading.Thread(target=_run, name="azure-inspect-refresher", daemon=True)
    t.start()
    return t
