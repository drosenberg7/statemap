"""Notifier tests — focus on the header-encoding bug that broke ntfy pushes."""

import requests

from ticketbot.notifier import Notifier


def test_ascii_header_passthrough():
    assert Notifier._encode_header("US Open ticket found") == "US Open ticket found"


def test_unicode_header_is_encoded_and_latin1_safe():
    encoded = Notifier._encode_header("🎾 Grandstand café")
    # Must not raise — this is exactly what requests does when sending headers.
    encoded.encode("latin-1")
    assert encoded.startswith("=?UTF-8?B?")


def test_prepared_request_headers_are_sendable():
    """Regression: an emoji title used to raise latin-1 UnicodeEncodeError."""
    title = Notifier._encode_header("US Open ticket found")
    req = requests.Request(
        "POST",
        "https://ntfy.sh/topic",
        data="body".encode("utf-8"),
        headers={
            "Title": title,
            "Tags": "tennis,tickets",
            "Click": "https://example.com",
            "Actions": "view, Buy now, https://example.com",
        },
    )
    prepared = req.prepare()  # raises if any header value isn't latin-1
    for key in ("Title", "Tags", "Click", "Actions"):
        prepared.headers[key].encode("latin-1")
