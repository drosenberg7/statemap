"""Decide whether a listing matches the user's criteria.

This is the brain of the bot and is deliberately free of any network I/O so it
can be unit-tested exhaustively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .config import Criteria
from .models import ARMSTRONG, ASHE, GRANDSTAND, GROUNDS, OTHER, Listing

# Text patterns used to classify a raw title/section into a canonical category.
# Order matters: more specific venues win. Grandstand is its own tier and is
# deliberately NOT the same as a general Grounds Pass.
_CATEGORY_PATTERNS = [
    (ASHE, re.compile(r"\barthur\s+ashe\b|\bashe\b", re.I)),
    (ARMSTRONG, re.compile(r"\blouis\s+armstrong\b|\barmstrong\b", re.I)),
    (GRANDSTAND, re.compile(r"\bgrandstand\b", re.I)),
    (GROUNDS, re.compile(r"\bgrounds?\b(\s+(pass|admission))?", re.I)),
]

# Night sessions at the US Open start in the evening; day sessions at 11am-ish.
# If a provider doesn't tell us, we infer from start time with this cutoff.
_NIGHT_CUTOFF_HOUR = 17  # 5pm ET


def classify_category(*texts: Optional[str]) -> str:
    """Map free-text (title, section, subcategory) to a canonical category.

    Ashe/Armstrong are checked before Grounds because a stadium ticket page
    often also contains the word "grounds"; the more specific venue wins.
    """
    blob = " ".join(t for t in texts if t)
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(blob):
            return category
    return OTHER


def infer_session(dt: Optional[datetime], *texts: Optional[str]) -> Optional[str]:
    """Determine day vs night from explicit text first, then start time."""
    blob = " ".join(t for t in texts if t).lower()
    if "night" in blob:
        return "night"
    if "day" in blob:
        return "day"
    if dt is not None:
        return "night" if dt.hour >= _NIGHT_CUTOFF_HOUR else "day"
    return None


@dataclass
class MatchResult:
    ok: bool
    reason: str


def enrich(listing: Listing) -> Listing:
    """Fill in category/session on a listing if the provider left them blank."""
    if listing.category in (OTHER, None):
        listing.category = classify_category(
            listing.event_title, listing.section
        )
    if listing.session is None:
        listing.session = infer_session(
            listing.event_datetime, listing.event_title, listing.section
        )
    return listing


def match(listing: Listing, criteria: Criteria) -> MatchResult:
    """Return whether a listing satisfies every criterion, with a reason."""
    enrich(listing)

    # 1. Price — the whole point. Strictly below the threshold.
    if listing.price is None:
        return MatchResult(False, "no price")
    if listing.price >= criteria.max_price:
        return MatchResult(False, f"price ${listing.price:.0f} >= ${criteria.max_price:.0f}")

    # 2. Category / venue.
    if listing.category not in criteria.categories:
        return MatchResult(False, f"category {listing.category} not wanted")

    # Curated events were hand-picked by the user for a specific session, so we
    # trust the date/session and only gate on price + category (done above).
    if listing.curated:
        return MatchResult(True, "match (curated)")

    # 3. Date.
    if listing.event_datetime is None:
        return MatchResult(False, "no event date")
    if listing.event_datetime.date() != criteria.target_date:
        return MatchResult(
            False,
            f"date {listing.event_datetime.date()} != {criteria.target_date}",
        )

    # 4. Session (day/night). "any" skips this check.
    if criteria.session != "any":
        if listing.session and listing.session != criteria.session:
            return MatchResult(False, f"session {listing.session} != {criteria.session}")

    return MatchResult(True, "match")
