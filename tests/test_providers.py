"""Tests for the pure parsing helpers of each provider (no network)."""

from ticketbot.providers.seatgeek import parse_platform_events
from ticketbot.providers.ticketmaster import parse_discovery
from ticketbot.providers.tickpick import parse_listings as tp_parse, parse_search
from ticketbot.providers.vividseats import parse_listings as vs_parse


def test_seatgeek_parse():
    payload = {
        "events": [
            {
                "id": 42,
                "title": "US Open Tennis - Arthur Ashe Stadium",
                "url": "https://seatgeek.com/e/42",
                "datetime_local": "2026-08-30T12:00:00",
                "venue": {"name": "Arthur Ashe Stadium"},
                "stats": {"lowest_price": 189},
            },
            {"id": 43, "title": "no price", "stats": {}},  # dropped
        ]
    }
    out = parse_platform_events(payload)
    assert len(out) == 1
    assert out[0].price == 189.0
    assert out[0].source == "seatgeek"
    assert out[0].section == "Arthur Ashe Stadium"
    assert out[0].event_datetime.hour == 12


def test_ticketmaster_parse():
    payload = {
        "_embedded": {
            "events": [
                {
                    "id": "G5v",
                    "name": "US Open Tennis Grounds Pass",
                    "url": "https://ticketmaster.com/x",
                    "dates": {"start": {"localDate": "2026-08-30", "localTime": "11:00:00"}},
                    "priceRanges": [{"min": 95, "max": 300}],
                    "_embedded": {"venues": [{"name": "USTA Billie Jean King"}]},
                }
            ]
        }
    }
    out = parse_discovery(payload)
    assert len(out) == 1
    assert out[0].price == 95.0
    assert out[0].event_datetime.hour == 11


def test_tickpick_parse_terse_keys():
    payload = {"l": [{"i": "1", "p": 210, "q": 2, "s": {"n": "Promenade"}}]}
    out = tp_parse(payload, "US Open Tennis", None, "http://tp/1")
    assert len(out) == 1
    assert out[0].price == 210.0
    assert out[0].quantity == 2
    assert out[0].fees_included is True
    assert out[0].section == "Promenade"


def test_tickpick_parse_verbose_keys():
    payload = {"listings": [{"id": "9", "price": 150, "quantity": 1, "section": "Loge"}]}
    out = tp_parse(payload, "US Open", None, "http://tp/9")
    assert out[0].price == 150.0
    assert out[0].section == "Loge"


def test_tickpick_search():
    payload = {"events": [{"i": "555", "n": "US Open Session 12", "d": "2026-08-30T12:00:00", "u": "http://tp/555"}]}
    events = parse_search(payload)
    assert events[0]["id"] == "555"
    assert events[0]["datetime"].year == 2026


def test_vividseats_parse():
    payload = {"tickets": [{"id": 7, "price": 240, "quantity": 3, "section": "Grandstand"}]}
    out = vs_parse(payload, "US Open", None, "http://vs")
    assert out[0].price == 240.0
    assert out[0].fees_included is False


def test_empty_payloads_are_safe():
    assert parse_platform_events({}) == []
    assert parse_discovery({}) == []
    assert tp_parse({}, "t", None, "u") == []
    assert vs_parse({}, "t", None, "u") == []
    assert parse_search({}) == []
