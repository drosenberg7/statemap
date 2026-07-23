"""TickPick provider.

TickPick is attractive for a price-threshold bot because its prices are
all-in (no surprise fees at checkout), so a listing under $275 here really is
under $275. TickPick has no official public API, but its site is backed by an
internal JSON endpoint we can call:

  * listings:  https://api.tickpick.com/1.0/listings/internal/event-v2/{id}

where {id} matches the /buy-tickets/{id} slug. Pin the exact events to watch
via config `tickpick_events` (id + venue) or the TICKPICK_EVENT_IDS env var,
which makes this provider both reliable and cheap.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.tickpick")

# The listings JSON is served by TickPick's internal API (confirmed from the
# site's own XHR). The event id matches the /buy-tickets/{id} slug. We keep an
# older shape as a fallback, then the event-page HTML as a last resort.
_LISTINGS_URLS = [
    "https://api.tickpick.com/1.0/listings/internal/event-v2/{event_id}?trackView=true",
    "https://www.tickpick.com/api/listings/{event_id}",
]
_EVENT_PAGE_URL = "https://www.tickpick.com/buy-tickets/{event_id}"
_SEARCH_URL = "https://www.tickpick.com/api/search-suggestions"
_QUERY = "US Open Tennis"

# api.tickpick.com expects requests to look like they come from the site.
_API_HEADERS = {
    "Origin": "https://www.tickpick.com",
    "Referer": "https://www.tickpick.com/",
    "Accept": "application/json, text/plain, */*",
}

# Keys that hold a per-ticket price across the various payload shapes.
_PRICE_KEYS = ("price", "p", "totalPrice", "displayPrice", "faceValue", "currentPrice")


def find_listings_array(obj) -> list:
    """Depth-first search for the first list of listing-like dicts in nested JSON.

    Works whether TickPick returns a bare array, a {"listings": [...]} object,
    or listings buried inside a Next.js __NEXT_DATA__ blob. A "listing-like"
    dict is one that carries a recognizable price key.
    """
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and any(k in obj[0] for k in _PRICE_KEYS):
            return obj
        for item in obj:
            hit = find_listings_array(item)
            if hit:
                return hit
    elif isinstance(obj, dict):
        for key in ("listings", "l"):
            v = obj.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        for v in obj.values():
            hit = find_listings_array(v)
            if hit:
                return hit
    return []


def extract_from_html(html: str) -> list:
    """Pull listing rows out of an event page's embedded JSON. Pure + testable."""
    # Next.js sites embed initial data in this script tag.
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S
    )
    if m:
        try:
            return find_listings_array(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    # Some builds assign a global state object instead.
    m = re.search(r'__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;\s*</script>', html, re.S)
    if m:
        try:
            return find_listings_array(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    return []


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
            rows = self._fetch_event_rows(ev["id"])
            parsed = parse_listings(
                {"listings": rows}, ev["title"], ev["datetime"], ev["url"]
            )
            for l in parsed:
                # A pinned event carries its venue + "trust me" flag.
                if ev.get("category"):
                    l.category = ev["category"]
                if ev.get("curated"):
                    l.curated = True
            if parsed:
                log.info("tickpick: event %s -> %d listing(s)", ev["id"], len(parsed))
            listings.extend(parsed)
        return listings

    def _fetch_event_rows(self, event_id: str) -> list:
        """Return raw listing dicts for one event, trying each source in turn."""
        # 1. JSON API candidates.
        for tmpl in _LISTINGS_URLS:
            url = tmpl.format(event_id=event_id)
            try:
                resp = self._get(url, headers=_API_HEADERS)
                log.info("tickpick: GET %s -> HTTP %s", url, resp.status_code)
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    log.info("tickpick: %s returned non-JSON body", url)
                    continue
                rows = find_listings_array(data)
                if rows:
                    log.info(
                        "tickpick: %d row(s) from %s; sample keys=%s",
                        len(rows), url, list(rows[0].keys())[:25],
                    )
                    return rows
                shape = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
                log.info("tickpick: %s 200 but no listings array; top-level=%s", url, shape)
            except Exception as exc:  # noqa: BLE001
                log.info("tickpick: api %s failed: %s", url, exc)
        # 2. Fall back to the data embedded in the event page HTML.
        try:
            resp = self._get(_EVENT_PAGE_URL.format(event_id=event_id))
            if resp.status_code == 200:
                rows = extract_from_html(resp.text)
                if rows:
                    log.info("tickpick: %d row(s) from HTML embed for %s", len(rows), event_id)
                    return rows
                log.warning(
                    "tickpick: event %s — no listings. The listings API 403'd above "
                    "(TickPick blocks datacenter IPs like GitHub's). Run from a "
                    "residential IP (Docker at home) or use the official APIs.", event_id,
                )
            else:
                log.warning("tickpick: event page %s -> HTTP %s", event_id, resp.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("tickpick: event %s fetch failed: %s", event_id, exc)
        return []

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
