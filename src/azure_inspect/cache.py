"""cache.py — small SQLite-backed TTL cache for Azure-Inspect.

Every dashboard request used to hit the live Azure REST API directly, which is
slow and risks rate-limiting. This module caches each (key, arg) result for a
configurable TTL so repeated loads (and the 60s auto-refresh) are served from
local storage. A background refresher can populate it so the dashboard is
instant; here we just provide the primitives + a sync helper.

The cache also records *when* each key was last successfully written, which
lets /health report data freshness instead of only "process is up".
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "azure_inspect.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataCache:
    def __init__(self, db_path: Optional[Path] = None):
        self.db = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, sqlite3.connect(self.db) as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                       key TEXT PRIMARY KEY,
                       value TEXT,
                       written_at TEXT
                   )"""
            )

    def get(self, key: str) -> Optional[tuple[Any, str]]:
        """Return (value, written_at_iso) if present, else None."""
        with self._lock, sqlite3.connect(self.db) as con:
            row = con.execute(
                "SELECT value, written_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0]), row[1]
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock, sqlite3.connect(self.db) as con:
            con.execute(
                "INSERT INTO cache(key, value, written_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "written_at=excluded.written_at",
                (key, json.dumps(value, default=_default), _now_iso()),
            )

    def written_at(self, key: str) -> Optional[str]:
        with self._lock, sqlite3.connect(self.db) as con:
            row = con.execute(
                "SELECT written_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def value(self, key: str) -> Any:
        """Return just the cached value (or None), without the timestamp."""
        hit = self.get(key)
        return hit[0] if hit is not None else None

    def cached(self, key: str, producer: Callable[[], Any], *,
               force: bool = False) -> Any:
        """Return cached value, refreshing via ``producer`` when missing/forced.

        On a producer error, returns the stale cached value if available
        (so a transient Azure outage doesn't blank the dashboard), otherwise
        re-raises so the existing error-classification path can show a banner.
        """
        if not force:
            hit = self.get(key)
            if hit is not None:
                return hit[0]
        try:
            value = producer()
        except Exception:
            stale = self.get(key)
            if stale is not None:
                return stale[0]
            raise
        self.set(key, value)
        return value


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)
