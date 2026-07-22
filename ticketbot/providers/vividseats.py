"""Vivid Seats provider.

Vivid Seats' site is backed by its "hermes" JSON API. Listings for an event
come from:

  https://www.vividseats.com/hermes/api/v1/listings?productionId={id}

As with TickPick, the reliable knob is pinning the production id(s) via
VIVIDSEATS_PRODUCTION_IDS (comma-separated). Heads up: Vivid Seats prices are
typically *pre-fee*, so a raw price under $275 may exceed $275 at checkout.
Tune your threshold accordingly (see notes in README).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..models import Listing
from .base import Provider

log = logging.getLogger("ticketbot.providers.vividseats")

_LISTINGS_URL = "https://www.vividseats.com/hermes/api/v1/listings"


def _parse_dt(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")[:19])
    except ValueError:
        return None


def parse_listings(payload: dict, event_title: str, event_dt, event_url: str) -> List[Listing]:
    """Turn a hermes listings payload into Listings. Pure + testable."""
    out: List[Listing] = []
    tickets = payload.get("tickets") or payload.get("listings") or []
    for t in tickets:
        price = t.get("price") or t.get("p")
        if price is None:
            continue
        section = t.get("section") or t.get("sectionName") or t.get("s")
        qty = t.get("quantity") or t.get("q")
        rid = t.get("id") or t.get("listingId")
        out.append(
            Listing(
                source="vividseats",
                event_title=event_title,
                price=float(price),
                url=event_url,
                event_datetime=event_dt,
                section=str(section) if section is not None else None,
                quantity=int(qty) if qty is not None else None,
                fees_included=False,  # Vivid Seats adds fees at checkout
                raw_id=str(rid) if rid is not None else None,
            )
        )
    return out


class VividSeatsProvider(Provider):
    name = "vividseats"

    def _fetch(self) -> List[Listing]:
        ids = os.environ.get("VIVIDSEATS_PRODUCTION_IDS", "").strip()
        if not ids:
            log.info("vividseats: set VIVIDSEATS_PRODUCTION_IDS to enable this provider")
            return []
        listings: List[Listing] = []
        for pid in [p.strip() for p in ids.split(",") if p.strip()]:
            try:
                resp = self._get(_LISTINGS_URL, params={"productionId": pid})
                resp.raise_for_status()
                url = f"https://www.vividseats.com/production/{pid}"
                listings.extend(parse_listings(resp.json(), "US Open Tennis", None, url))
            except Exception as exc:  # noqa: BLE001
                log.warning("vividseats: production %s failed: %s", pid, exc)
        return listings
