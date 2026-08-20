"""alerts.py — optional Telegram alerts for Azure-Inspect (secret-safe).

Reuses the same Telegram bot + channel as the rest of the homelab stack:
TELEGRAM_BOT_TOKEN + TELEGRAM_HOME_CHANNEL are read from ~/.hermes/.env at
call time. No token is embedded in source or passed on a command line.

If Telegram is unconfigured or the request fails, send() returns False (never
raises) so alerting can never break the refresh loop.

Alert cooldown: each alert type is rate-limited via a small SQLite table so the
same condition can't spam the channel (e.g. a sustained spend spike alerts once
per COOLDOWN_HOURS, not every 15-minute refresh).
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

_ENV_PATH = Path.home() / ".hermes" / ".env"
_DB_PATH = Path.home() / "code" / "Azure-Inspect" / "azure_inspect.db"

COOLDOWN_SECONDS = 12 * 3600  # 12h per alert type


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def send(message: str) -> bool:
    """Post ``message`` to the configured Telegram channel. Best-effort."""
    import requests

    env = _read_env(_ENV_PATH)
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = env.get("TELEGRAM_HOME_CHANNEL", "").strip()
    if not token or not channel:
        return False
    thread = env.get("TELEGRAM_HOME_CHANNEL_THREAD_ID", "").strip()
    payload: dict[str, object] = {
        "chat_id": channel,
        "text": message,
        "disable_web_page_preview": True,
    }
    if thread:
        payload["message_thread_id"] = thread
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _last_alerted(key: str) -> float:
    try:
        con = sqlite3.connect(_DB_PATH)
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS alert_cooldown (key TEXT PRIMARY KEY, ts REAL)")
        row = cur.execute("SELECT ts FROM alert_cooldown WHERE key=?", (key,)).fetchone()
        con.close()
        return row[0] if row else 0.0
    except sqlite3.Error:
        return 0.0


def _mark_alerted(key: str) -> None:
    try:
        con = sqlite3.connect(_DB_PATH)
        con.execute(
            "CREATE TABLE IF NOT EXISTS alert_cooldown (key TEXT PRIMARY KEY, ts REAL)"
        )
        con.execute(
            "INSERT INTO alert_cooldown(key, ts) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET ts=excluded.ts",
            (key, time.time()),
        )
        con.commit()
        con.close()
    except sqlite3.Error:
        pass


def alert(key: str, message: str) -> bool:
    """Send ``message`` only if ``key`` hasn't fired within COOLDOWN_SECONDS.

    Returns True if an alert was actually sent.
    """
    now = time.time()
    if now - _last_alerted(key) < COOLDOWN_SECONDS:
        return False
    if send(message):
        _mark_alerted(key)
        return True
    return False
