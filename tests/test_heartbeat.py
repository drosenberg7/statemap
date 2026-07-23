"""Heartbeat behavior: fires when due, stays quiet otherwise, reports cheapest."""

from datetime import date, datetime

from ticketbot.config import Config, Criteria
from ticketbot.models import ASHE, GROUNDS, Listing
from ticketbot.monitor import Monitor
from ticketbot.state import SeenState


class FakeProvider:
    def __init__(self, listings):
        self._listings = listings

    def fetch(self):
        return list(self._listings)


class RecordingNotifier:
    def __init__(self):
        self.alerts = []
        self.texts = []

    def notify(self, listing):
        self.alerts.append(listing)

    def send_text(self, title, body):
        self.texts.append((title, body))


def _config(tmp_path, heartbeat_hours):
    return Config(
        criteria=Criteria(date(2026, 8, 30), "day", [GROUNDS, ASHE], 275.0),
        providers=[],
        poll_interval_seconds=1,
        poll_jitter_seconds=0,
        heartbeat_hours=heartbeat_hours,
        ntfy_topic="",
        ntfy_server="https://ntfy.sh",
        notifiers=["console"],
        state_path=str(tmp_path / "state.json"),
    )


def _monitor(tmp_path, listings, heartbeat_hours):
    cfg = _config(tmp_path, heartbeat_hours)
    m = Monitor.__new__(Monitor)
    m.config = cfg
    m.providers = [FakeProvider(listings)]
    m.notifier = RecordingNotifier()
    m.state = SeenState(cfg.state_path)
    return m


def _ashe(price):
    return Listing(source="sg", event_title="US Open - Session 1", price=price,
                   url="http://x", event_datetime=datetime(2026, 8, 30, 12, 0),
                   section="Arthur Ashe Stadium")


def test_heartbeat_fires_first_time(tmp_path):
    m = _monitor(tmp_path, [_ashe(400)], heartbeat_hours=24)  # 400 = no price match
    m.poll_once()
    assert len(m.notifier.texts) == 1
    assert "no match yet" in m.notifier.texts[0][1].lower()


def test_heartbeat_reports_cheapest(tmp_path):
    m = _monitor(tmp_path, [_ashe(400), _ashe(320)], heartbeat_hours=24)
    m.poll_once()
    _, body = m.notifier.texts[0]
    assert "$320" in body  # cheapest for the session, even though above $275


def test_heartbeat_not_repeated_within_window(tmp_path):
    m = _monitor(tmp_path, [_ashe(400)], heartbeat_hours=24)
    m.poll_once()
    m.poll_once()
    assert len(m.notifier.texts) == 1  # second cycle is within the window


def test_heartbeat_disabled(tmp_path):
    m = _monitor(tmp_path, [_ashe(400)], heartbeat_hours=0)
    m.poll_once()
    assert m.notifier.texts == []


def test_heartbeat_does_not_replace_real_alert(tmp_path):
    m = _monitor(tmp_path, [_ashe(249)], heartbeat_hours=24)
    m.poll_once()
    assert len(m.notifier.alerts) == 1   # real match still alerts
    assert len(m.notifier.texts) == 1    # and heartbeat still fires
