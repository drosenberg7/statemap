"""Ticketmaster provider.

US Open sessions are sold on Ticketmaster. The Discovery API
(app.ticketmaster.com/discovery/v2) is the reliable path and is used when
TICKETMASTER_API_KEY is present — it exposes `priceRanges` per event. Without a
key we do a best-effort fetch of the public Discovery endpoint's demo tier,
which is rate-limited and may return nothing; treat scrape mode as flaky.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.ticketmaster")

_DISCOVERY_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
_KEYWORD = "US Open Tennis"


def _parse_dt(ev: dict):
    dates = (ev.get("dates") or {}).get("start") or {}
    local = dates.get("localDate")
    time_ = dates.get("localTime")
    if not local:
        return None
    try:
        if time_:
            return datetime.fromisoformat(f"{local}T{time_}")
        return datetime.fromisoformat(f"{local}T00:00:00")
    except ValueError:
        return None


def parse_discovery(payload: dict) -> List[Listing]:
    """Turn a Discovery API response into listings. Pure + testable."""
    out: List[Listing] = []
    events = ((payload.get("_embedded") or {}).get("events")) or []
    for ev in events:
        price = None
        for pr in ev.get("priceRanges", []) or []:
            candidate = pr.get("min")
            if candidate is not None:
                price = candidate if price is None else min(price, candidate)
        if price is None:
            continue
        venues = ((ev.get("_embedded") or {}).get("venues")) or []
        venue_name = venues[0].get("name") if venues else None
        out.append(
            Listing(
                source="ticketmaster",
                event_title=ev.get("name", "US Open Tennis"),
                price=float(price),
                url=ev.get("url", "https://www.ticketmaster.com"),
                event_datetime=_parse_dt(ev),
                section=venue_name,
                fees_included=False,
                raw_id=ev.get("id"),
            )
        )
    return out


class TicketmasterProvider(Provider):
    name = "ticketmaster"

    def _fetch(self) -> List[Listing]:
        api_key = os.environ.get("TICKETMASTER_API_KEY")
        if not api_key:
            log.info("ticketmaster: no API key set; skipping (Discovery API requires one)")
            return []
        target = self.config.criteria.target_date.isoformat()
        resp = self._get(
            _DISCOVERY_URL,
            params={
                "apikey": api_key,
                "keyword": _KEYWORD,
                "startDateTime": f"{target}T00:00:00Z",
                "endDateTime": f"{target}T23:59:59Z",
                "size": 50,
            },
        )
        resp.raise_for_status()
        return parse_discovery(resp.json())
