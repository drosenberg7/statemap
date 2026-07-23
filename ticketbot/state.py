"""Persistent de-duplication so we only alert once per listing.

The repo is called "statemap" for a reason: this is a small on-disk map from
listing id -> the last price we alerted at. We re-alert only when a listing
reappears at a meaningfully lower price, so a price drop still reaches you but
identical re-scrapes stay quiet.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Dict


class SeenState:
    def __init__(self, path: str):
        self.path = path
        self._map: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self._map = json.load(fh)
            except (json.JSONDecodeError, OSError):
                # Corrupt/empty state file: start fresh rather than crash.
                self._map = {}

    def _save(self) -> None:
        # Atomic write so a crash mid-write can't corrupt the state file.
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._map, fh, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def should_notify(self, listing_id: str, price: float, drop_pct: float = 0.0) -> bool:
        """True if this is new, or reappeared at a lower price worth flagging.

        drop_pct: require at least this fractional price drop to re-notify an
        already-seen listing (0.0 = any drop re-notifies).
        """
        prev = self._map.get(listing_id)
        if prev is None:
            return True
        prev_price = prev.get("price")
        if prev_price is None:
            return True
        if price < prev_price * (1.0 - drop_pct):
            return True
        return False

    def record(self, listing_id: str, price: float) -> None:
        self._map[listing_id] = {"price": price, "ts": time.time()}
        self._save()

    # Heartbeat bookkeeping. Stored under a reserved key so it never collides
    # with a listing id (which are 16-hex).
    _HEARTBEAT_KEY = "__heartbeat__"

    def seconds_since_heartbeat(self) -> float:
        ts = self._map.get(self._HEARTBEAT_KEY, {}).get("ts")
        return float("inf") if ts is None else time.time() - ts

    def mark_heartbeat(self) -> None:
        self._map[self._HEARTBEAT_KEY] = {"ts": time.time()}
        self._save()

    def __len__(self) -> int:
        return len(self._map)
