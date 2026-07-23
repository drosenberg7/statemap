from datetime import date, datetime

from ticketbot.config import Criteria
from ticketbot.matcher import classify_category, infer_session, match
from ticketbot.models import ARMSTRONG, ASHE, GRANDSTAND, GROUNDS, OTHER, Listing


CRIT = Criteria(
    target_date=date(2026, 8, 30),
    session="day",
    categories=[GROUNDS, ASHE, ARMSTRONG],
    max_price=275.0,
)


def _listing(**kw):
    base = dict(
        source="test",
        event_title="US Open Tennis",
        price=200.0,
        url="http://x",
        event_datetime=datetime(2026, 8, 30, 12, 0),
    )
    base.update(kw)
    return Listing(**base)


# ---- category classification ---------------------------------------------

def test_classify_ashe():
    assert classify_category("US Open — Arthur Ashe Stadium") == ASHE

def test_classify_armstrong():
    assert classify_category("Louis Armstrong Stadium Day Session") == ARMSTRONG

def test_classify_grounds():
    assert classify_category("US Open Grounds Pass") == GROUNDS

def test_grandstand_is_its_own_category_not_grounds():
    # Grandstand is a distinct tier from a general Grounds Pass.
    assert classify_category(
        "US Open Tennis - Day Session 1 (Grandstand Only)",
        "Grandstand at the Billie Jean King Tennis Center",
    ) == GRANDSTAND

def test_billie_jean_king_center_is_grounds():
    # Ticketmaster's bare complex venue = general grounds admission.
    assert classify_category(
        "Men's/Women's First Round", "Billie Jean King National Tennis Center"
    ) == GROUNDS

def test_grandstand_not_tracked_by_default():
    # Default criteria wants grounds/ashe/armstrong — a grandstand listing is skipped.
    l = _listing(price=100, event_title="US Open Tennis (Grandstand Only)",
                 section="Grandstand at the Billie Jean King Tennis Center")
    assert not match(l, CRIT).ok

def test_specific_venue_beats_grounds():
    # A stadium page that also mentions "grounds" should classify as the stadium.
    assert classify_category("Arthur Ashe Stadium (includes grounds access)") == ASHE

def test_classify_other():
    assert classify_category("US Open Suite Experience") == OTHER


# ---- session inference ----------------------------------------------------

def test_session_from_text():
    assert infer_session(None, "Ashe Night Session") == "night"

def test_session_from_time_day():
    assert infer_session(datetime(2026, 8, 30, 11, 0)) == "day"

def test_session_from_time_night():
    assert infer_session(datetime(2026, 8, 30, 19, 0)) == "night"


# ---- full match -----------------------------------------------------------

def test_full_match():
    r = match(_listing(price=249, section="Arthur Ashe Stadium"), CRIT)
    assert r.ok, r.reason

def test_price_at_threshold_rejected():
    r = match(_listing(price=275, section="Ashe"), CRIT)
    assert not r.ok and "price" in r.reason

def test_price_above_rejected():
    assert not match(_listing(price=300, section="Ashe"), CRIT).ok

def test_wrong_date_rejected():
    r = match(_listing(event_datetime=datetime(2026, 8, 31, 12, 0), section="Ashe"), CRIT)
    assert not r.ok and "date" in r.reason

def test_wrong_session_rejected():
    r = match(_listing(event_datetime=datetime(2026, 8, 30, 19, 0), section="Ashe"), CRIT)
    assert not r.ok and "session" in r.reason

def test_wrong_category_rejected():
    r = match(_listing(section="VIP Suite", event_title="US Open Luxury Suite Experience"), CRIT)
    assert not r.ok and "category" in r.reason

def test_grounds_match():
    r = match(_listing(event_title="US Open Grounds Pass", section=None), CRIT)
    assert r.ok, r.reason

def test_any_session_allows_night():
    crit = Criteria(date(2026, 8, 30), "any", [ASHE], 275)
    r = match(_listing(event_datetime=datetime(2026, 8, 30, 19, 0), section="Ashe"), crit)
    assert r.ok, r.reason

def test_missing_date_rejected():
    assert not match(_listing(event_datetime=None, section="Ashe"), CRIT).ok


# ---- curated (user-pinned) events ----------------------------------------

def test_curated_skips_date_and_session():
    # No date, evening time -> would normally fail, but curated trusts it.
    l = _listing(price=199, event_datetime=None, section=None, category=ASHE, curated=True)
    r = match(l, CRIT)
    assert r.ok and "curated" in r.reason

def test_curated_still_enforces_price():
    l = _listing(price=300, event_datetime=None, category=ASHE, curated=True)
    assert not match(l, CRIT).ok

def test_curated_still_enforces_category():
    crit = Criteria(date(2026, 8, 30), "day", [ASHE], 275)  # only Ashe wanted
    l = _listing(price=199, event_datetime=None, category=GROUNDS, curated=True)
    assert not match(l, crit).ok
