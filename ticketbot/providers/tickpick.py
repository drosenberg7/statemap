"""TickPick provider.

TickPick is attractive for a price-threshold bot because its prices are
all-in (no surprise fees at checkout), so a listing under $275 here really is
under $275. TickPick has no official public API, but its site is backed by JSON
endpoints we can call best-effort:

  * search:    https://www.tickpick.com/api/search/...        (find event ids)
  * listings:  https://www.tickpick.com/api/listings/{id}     (offers for an event)

Because discovery-by-search is the most fragile part, you can pin the event ids
directly via the TICKPICK_EVENT_IDS env var (comma-separated) once you know
them, which makes this provider both reliable and cheap.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.tickpick")

_LISTINGS_URL = "https://www.tickpick.com/api/listings/{event_id}"
_SEARCH_URL = "https://www.tickpick.com/api/search-suggestions"
_QUERY = "US Open Tennis"


def _parse_dt(value: Optional[str]):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def parse_listings(payload: dict, event_title: str, event_dt, event_url: str) -> List[Listing]:
    """Turn a TickPick listings payload into Listings. Pure + testable.

    TickPick's listing objects are terse; we defensively read several possible
    keys for price/quantity/section since the exact shape drifts over time.
    """
    out: List[Listing] = []
    rows = payload.get("listings")
    if rows is None:
        rows = payload.get("l", [])
    for row in rows or []:
        price = row.get("price", row.get("p"))
        if price is None:
            continue
        section = row.get("section", row.get("s"))
        if isinstance(section, dict):
            section = section.get("name") or section.get("n")
        qty = row.get("quantity", row.get("q"))
        rid = row.get("id", row.get("i"))
        out.append(
            Listing(
                source="tickpick",
                event_title=event_title,
                price=float(price),
                url=event_url,
                event_datetime=event_dt,
                section=str(section) if section is not None else None,
                quantity=int(qty) if qty is not None else None,
                fees_included=True,  # TickPick is all-in pricing
                raw_id=str(rid) if rid is not None else None,
            )
        )
    return out


def parse_search(payload: dict) -> List[dict]:
    """Extract candidate events {id, title, datetime, url} from a search payload."""
    events: List[dict] = []
    # The suggestions endpoint groups results; events usually live under an
    # "events" or "e" key. Walk defensively.
    buckets = []
    if isinstance(payload, dict):
        buckets = payload.get("events") or payload.get("e") or payload.get("results") or []
    for item in buckets:
        eid = item.get("id") or item.get("i")
        if eid is None:
            continue
        events.append(
            {
                "id": str(eid),
                "title": item.get("name") or item.get("n") or "US Open Tennis",
                "datetime": _parse_dt(item.get("date") or item.get("d")),
                "url": item.get("url") or item.get("u") or "https://www.tickpick.com",
            }
        )
    return events


class TickPickProvider(Provider):
    name = "tickpick"

    def _fetch(self) -> List[Listing]:
        events = self._discover_events()
        listings: List[Listing] = []
        for ev in events:
            try:
                resp = self._get(_LISTINGS_URL.format(event_id=ev["id"]))
                resp.raise_for_status()
                parsed = parse_listings(resp.json(), ev["title"], ev["datetime"], ev["url"])
                for l in parsed:
                    # A pinned event carries its venue + "trust me" flag.
                    if ev.get("category"):
                        l.category = ev["category"]
                    if ev.get("curated"):
                        l.curated = True
                listings.extend(parsed)
            except Exception as exc:  # noqa: BLE001
                log.warning("tickpick: listings for event %s failed: %s", ev["id"], exc)
        return listings

    def _discover_events(self) -> List[dict]:
        # 1. Per-event pins from config (id + venue) — most reliable.
        cfg_events = getattr(self.config, "tickpick_events", None) or []
        if cfg_events:
            return [
                {"id": e["id"], "category": e.get("category"),
                 "title": e.get("label", "US Open Tennis"), "datetime": None,
                 "url": f"https://www.tickpick.com/buy-tickets/{e['id']}",
                 "curated": True}
                for e in cfg_events
            ]
        # 2. Bare ids from the environment (no venue mapping).
        pinned = os.environ.get("TICKPICK_EVENT_IDS", "").strip()
        if pinned:
            return [
                {"id": eid.strip(), "category": None, "title": "US Open Tennis",
                 "datetime": None,
                 "url": f"https://www.tickpick.com/buy-tickets/{eid.strip()}",
                 "curated": True}
                for eid in pinned.split(",")
                if eid.strip()
            ]
        # 3. Fall back to search (fragile).
        try:
            resp = self._get(_SEARCH_URL, params={"q": _QUERY})
            resp.raise_for_status()
            return parse_search(resp.json())
        except Exception as exc:  # noqa: BLE001
            log.warning("tickpick: search failed (%s); set TICKPICK_EVENT_IDS to pin events", exc)
            return []
