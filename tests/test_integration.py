"""End-to-end poll cycle with a fake provider and recording notifier."""

from datetime import date, datetime

from ticketbot.config import Config, Criteria
from ticketbot.models import ASHE, GROUNDS, Listing
from ticketbot.monitor import Monitor


class FakeProvider:
    def __init__(self, listings):
        self._listings = listings

    def fetch(self):
        return list(self._listings)


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, listing):
        self.sent.append(listing)


def _config(tmp_path):
    return Config(
        criteria=Criteria(date(2026, 8, 30), "day", [GROUNDS, ASHE], 275.0),
        providers=[],  # we inject providers manually
        poll_interval_seconds=1,
        poll_jitter_seconds=0,
        ntfy_topic="",
        ntfy_server="https://ntfy.sh",
        notifiers=["console"],
        state_path=str(tmp_path / "state.json"),
    )


def _monitor(tmp_path, listings):
    cfg = _config(tmp_path)
    m = Monitor.__new__(Monitor)  # bypass __init__ to inject fakes
    m.config = cfg
    from ticketbot.state import SeenState
    m.providers = [FakeProvider(listings)]
    m.notifier = RecordingNotifier()
    m.state = SeenState(cfg.state_path)
    return m


def _mk(price, dt_hour=12, section="Arthur Ashe Stadium", **kw):
    fields = dict(
        source="fake",
        event_title="US Open Tennis",
        price=price,
        url="http://x",
        event_datetime=datetime(2026, 8, 30, dt_hour, 0),
        section=section,
    )
    fields.update(kw)  # let callers override any default
    return Listing(**fields)


def test_matching_listing_notifies_once(tmp_path):
    listing = _mk(249)
    m = _monitor(tmp_path, [listing])

    matched = m.poll_once()
    assert len(matched) == 1
    assert len(m.notifier.sent) == 1

    # Second cycle with the same listing -> no duplicate alert.
    m.poll_once()
    assert len(m.notifier.sent) == 1


def test_filters_applied(tmp_path):
    listings = [
        _mk(300),                              # too expensive
        _mk(249, dt_hour=19),                  # night session
        _mk(249, section="Suite", event_title="US Open Suite"),  # wrong category
        _mk(199),                              # keeper
    ]
    m = _monitor(tmp_path, listings)
    matched = m.poll_once()
    assert len(matched) == 1
    assert matched[0].price == 199


def test_price_drop_renotifies(tmp_path):
    m = _monitor(tmp_path, [_mk(249, raw_id="same")])
    m.poll_once()
    assert len(m.notifier.sent) == 1
    # Same listing id, lower price -> alert again.
    m.providers = [FakeProvider([_mk(199, raw_id="same")])]
    m.poll_once()
    assert len(m.notifier.sent) == 2
