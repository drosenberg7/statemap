"""SeatGeek provider.

Primary path uses the official SeatGeek Platform API when a client id is present
(SEATGEEK_CLIENT_ID); it's stable and returns a per-event `stats.lowest_price`
which is exactly what we filter on. Without a key we fall back to parsing the
JSON that SeatGeek embeds in its search page HTML (best-effort, fragile).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import List

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.seatgeek")

_PLATFORM_URL = "https://api.seatgeek.com/2/events"
_SEARCH_URL = "https://seatgeek.com/search"
_QUERY = "US Open Tennis"


def _parse_dt(value):
    if not value:
        return None
    try:
        # SeatGeek datetime_local looks like "2026-08-30T11:00:00".
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def parse_platform_events(payload: dict) -> List[Listing]:
    """Turn a SeatGeek /2/events response into listings. Pure + testable."""
    out: List[Listing] = []
    for ev in payload.get("events", []):
        stats = ev.get("stats") or {}
        price = stats.get("lowest_price")
        if price is None:
            price = stats.get("lowest_price_good_deals")
        if price is None:
            continue
        venue = (ev.get("venue") or {}).get("name")
        title = ev.get("title") or ev.get("short_title") or "US Open Tennis"
        out.append(
            Listing(
                source="seatgeek",
                event_title=title,
                price=float(price),
                url=ev.get("url", "https://seatgeek.com"),
                event_datetime=_parse_dt(ev.get("datetime_local")),
                section=venue,
                fees_included=False,
                raw_id=str(ev.get("id")) if ev.get("id") is not None else None,
            )
        )
    return out


class SeatGeekProvider(Provider):
    name = "seatgeek"

    def _fetch(self) -> List[Listing]:
        client_id = os.environ.get("SEATGEEK_CLIENT_ID")
        if client_id:
            return self._fetch_api(client_id)
        return self._fetch_scrape()

    def _fetch_api(self, client_id: str) -> List[Listing]:
        # Query broadly by keyword and let the matcher pin down the exact date /
        # session / venue. API-side date filtering was too brittle (timezone +
        # how SeatGeek dates its sessions), so we pull the US Open events and
        # filter locally. Rich logging so the response shape is visible.
        resp = self._get(
            _PLATFORM_URL,
            params={
                "client_id": client_id,
                "q": _QUERY,
                "per_page": 100,
            },
        )
        log.info("seatgeek: GET %s -> HTTP %s", _PLATFORM_URL, resp.status_code)
        resp.raise_for_status()
        payload = resp.json()
        total = (payload.get("meta") or {}).get("total")
        events = payload.get("events", [])
        log.info("seatgeek: meta.total=%s, events_in_page=%d", total, len(events))
        for ev in events[:8]:
            stats = ev.get("stats") or {}
            log.debug(
                "seatgeek: - %s | %s | %s | low=$%s",
                ev.get("title"),
                (ev.get("venue") or {}).get("name"),
                ev.get("datetime_local"),
                stats.get("lowest_price"),
            )
        return parse_platform_events(payload)

    def _fetch_scrape(self) -> List[Listing]:
        resp = self._get(_SEARCH_URL, params={"q": _QUERY})
        resp.raise_for_status()
        return self._parse_search_html(resp.text)

    @staticmethod
    def _parse_search_html(html: str) -> List[Listing]:
        """Best-effort: pull the embedded Redux/JSON blob and reuse the API parser."""
        # SeatGeek embeds preloaded data in a script tag; the exact key changes
        # over time so we look for an "events" array heuristically.
        match = re.search(r'"events"\s*:\s*(\[.*?\])\s*,\s*"meta"', html, re.S)
        if not match:
            log.info("seatgeek: no embedded events blob found (markup changed?)")
            return []
        try:
            events = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
        return parse_platform_events({"events": events})
