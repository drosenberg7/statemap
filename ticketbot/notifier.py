"""Notification backends. Default channel is ntfy.sh push."""

from __future__ import annotations

import json
import logging
import smtplib
from email.mime.text import MIMEText
from typing import List

import requests

from .config import Config
from .models import Listing

log = logging.getLogger("ticketbot.notifier")


class Notifier:
    """Fans a match out to every configured channel. Never raises."""

    def __init__(self, config: Config):
        self.config = config
        self.channels = config.notifiers

    def notify(self, listing: Listing) -> None:
        # Keep the title plain ASCII: HTTP headers (used by ntfy) are latin-1,
        # so an emoji here throws. ntfy renders the 🎾 from the "tennis" tag.
        self._emit(
            "US Open ticket found", listing.summary(), url=listing.url,
            tags="tennis,tickets", priority="high",
        )

    def send_text(self, title: str, body: str) -> None:
        """Send a plain informational message (e.g. the alive heartbeat)."""
        self._emit(title, body, url="", tags="tennis,green_circle", priority="low")

    def _emit(self, title: str, body: str, url: str, tags: str, priority: str) -> None:
        for channel in self.channels:
            try:
                if channel == "ntfy":
                    self._ntfy(title, body, url, tags, priority)
                elif channel == "console":
                    self._console(title, body, url)
                elif channel == "email":
                    self._email(title, body, url)
                elif channel == "webhook":
                    self._webhook(title, body, url)
                else:
                    log.warning("unknown notify channel: %s", channel)
            except Exception as exc:  # noqa: BLE001 - alerts must never crash the loop
                log.error("notify via %s failed: %s", channel, exc)

    # -- channels -----------------------------------------------------------

    @staticmethod
    def _encode_header(value: str) -> str:
        """Make a header value safe for HTTP (latin-1).

        Defensive: if a value ever contains non-latin-1 characters (emoji,
        accented section names, …) we RFC 2047-encode it, which ntfy decodes
        back to the original. ASCII values pass through untouched.
        """
        try:
            value.encode("latin-1")
            return value
        except UnicodeEncodeError:
            import base64
            return "=?UTF-8?B?" + base64.b64encode(value.encode("utf-8")).decode("ascii") + "?="

    def _console(self, title: str, body: str, url: str) -> None:
        tail = f"\n{url}" if url else ""
        print(f"\n*** 🎾 {title} ***\n{body}{tail}\n", flush=True)

    def _ntfy(self, title: str, body: str, url: str, tags: str, priority: str) -> None:
        topic = self.config.ntfy_topic
        if not topic:
            log.warning("ntfy channel active but NTFY_TOPIC is empty; skipping")
            return
        server = self.config.ntfy_server.rstrip("/")
        headers = {
            "Title": self._encode_header(title),
            "Priority": priority,
            "Tags": tags,
        }
        # Only attach a click target / buy button when there's a real listing.
        if url:
            headers["Click"] = url
            headers["Actions"] = f"view, Buy now, {url}"
        requests.post(
            f"{server}/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=self.config.request_timeout,
        ).raise_for_status()

    def _email(self, title: str, body: str, url: str) -> None:
        cfg = self.config.extra["email"]
        if not (cfg["smtp_host"] and cfg["to_addr"]):
            log.warning("email channel active but SMTP not configured; skipping")
            return
        msg = MIMEText(f"{body}\n\n{url}")
        msg["Subject"] = title
        msg["From"] = cfg["from_addr"] or cfg["smtp_user"]
        msg["To"] = cfg["to_addr"]
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=self.config.request_timeout) as srv:
            srv.starttls()
            if cfg["smtp_user"]:
                srv.login(cfg["smtp_user"], cfg["smtp_password"])
            srv.send_message(msg)

    def _webhook(self, title: str, body: str, url: str) -> None:
        cfg = self.config.extra["webhook"]
        if not cfg["url"]:
            log.warning("webhook channel active but WEBHOOK_URL is empty; skipping")
            return
        text = f"{title}\n{body}" + (f"\n{url}" if url else "")
        # A shape that works for both Slack ("text") and Discord ("content").
        payload = {"text": text, "content": text}
        requests.post(
            cfg["url"],
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self.config.request_timeout,
        ).raise_for_status()
