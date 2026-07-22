"""StubHub provider (stub).

StubHub aggressively blocks unauthenticated automated access and requires OAuth
credentials for its Partner API. Rather than ship a scraper that will be blocked
and possibly violate their terms, this provider is a documented no-op unless you
supply real API credentials. If you have a StubHub Partner account, set
STUBHUB_APP_TOKEN and implement `_fetch_api` against the inventory search
endpoint; the parsing helper below is ready to normalize the response.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.stubhub")


def _parse_dt(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")[:19])
    except ValueError:
        return None


def parse_inventory(payload: dict, event_title: str, event_url: str) -> List[Listing]:
    """Normalize a StubHub inventory response. Pure + testable."""
    out: List[Listing] = []
    for l in payload.get("listing", []) or []:
        price = (l.get("currentPrice") or {}).get("amount") if isinstance(l.get("currentPrice"), dict) else l.get("currentPrice")
        if price is None:
            continue
        out.append(
            Listing(
                source="stubhub",
                event_title=event_title,
                price=float(price),
                url=event_url,
                event_datetime=_parse_dt(l.get("eventDate")),
                section=l.get("sectionName"),
                quantity=l.get("quantity"),
                fees_included=False,
                raw_id=str(l.get("listingId")) if l.get("listingId") is not None else None,
            )
        )
    return out


class StubHubProvider(Provider):
    name = "stubhub"

    def _fetch(self) -> List[Listing]:
        token = os.environ.get("STUBHUB_APP_TOKEN")
        if not token:
            log.info("stubhub: disabled (needs Partner API creds via STUBHUB_APP_TOKEN)")
            return []
        # Left intentionally unimplemented — plug in the StubHub inventory
        # search endpoint here and feed the JSON to parse_inventory().
        log.info("stubhub: token present but API call not implemented; see stubhub.py")
        return []
