"""Core data structures shared across providers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Canonical category identifiers used everywhere in the bot.
GROUNDS = "grounds"
ASHE = "ashe"
ARMSTRONG = "armstrong"
GRANDSTAND = "grandstand"
OTHER = "other"

CATEGORY_LABELS = {
    GROUNDS: "Grounds Pass",
    ASHE: "Arthur Ashe Stadium",
    ARMSTRONG: "Louis Armstrong Stadium",
    GRANDSTAND: "Grandstand",
    OTHER: "Other",
}


@dataclass
class Listing:
    """A single ticket listing / offer found on a marketplace.

    Providers normalize whatever they scrape into this shape so the matcher and
    notifier can stay provider-agnostic.
    """

    source: str                       # provider name, e.g. "tickpick"
    event_title: str                  # raw event title from the site
    price: float                      # per-ticket price in USD (incl. fees if known)
    url: str                          # link a human can click to buy
    event_datetime: Optional[datetime] = None  # local (ET) event start
    session: Optional[str] = None     # "day" | "night" | None (inferred if missing)
    category: str = OTHER             # one of GROUNDS/ASHE/ARMSTRONG/OTHER
    section: Optional[str] = None     # raw section/zone text if available
    quantity: Optional[int] = None    # number of seats in the listing
    fees_included: bool = False       # whether `price` already includes fees
    raw_id: Optional[str] = None      # provider-native id, if any
    curated: bool = False             # user pinned this exact event -> trust it,
                                      # skip date/session filtering (price still applies)

    # Populated by __post_init__.
    id: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.id = self._compute_id()

    def _compute_id(self) -> str:
        """Stable identity used for de-duplication across polling cycles.

        Two scrapes of the same underlying offer should produce the same id so
        we don't notify twice. We deliberately exclude price so a price *drop*
        on the same listing still counts as "seen" — price changes are handled
        by the matcher/state layer, not identity.
        """
        if self.raw_id:
            basis = f"{self.source}:{self.raw_id}"
        else:
            dt = self.event_datetime.isoformat() if self.event_datetime else "?"
            basis = f"{self.source}:{self.category}:{self.section}:{dt}:{self.url}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    def summary(self) -> str:
        cat = CATEGORY_LABELS.get(self.category, self.category)
        when = self.event_datetime.strftime("%a %b %d %I:%M %p") if self.event_datetime else "date TBD"
        sess = f" ({self.session})" if self.session else ""
        sec = f" — {self.section}" if self.section else ""
        qty = f" x{self.quantity}" if self.quantity else ""
        return f"${self.price:.0f}{qty} · {cat}{sec} · {when}{sess} · {self.source}"
