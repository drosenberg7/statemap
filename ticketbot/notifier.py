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
        title = "🎾 US Open ticket found"
        body = listing.summary()
        for channel in self.channels:
            try:
                if channel == "ntfy":
                    self._ntfy(title, body, listing.url)
                elif channel == "console":
                    self._console(title, body, listing.url)
                elif channel == "email":
                    self._email(title, body, listing.url)
                elif channel == "webhook":
                    self._webhook(title, body, listing)
                else:
                    log.warning("unknown notify channel: %s", channel)
            except Exception as exc:  # noqa: BLE001 - alerts must never crash the loop
                log.error("notify via %s failed: %s", channel, exc)

    # -- channels -----------------------------------------------------------

    def _console(self, title: str, body: str, url: str) -> None:
        print(f"\n*** {title} ***\n{body}\n{url}\n", flush=True)

    def _ntfy(self, title: str, body: str, url: str) -> None:
        topic = self.config.ntfy_topic
        if not topic:
            log.warning("ntfy channel active but NTFY_TOPIC is empty; skipping")
            return
        server = self.config.ntfy_server.rstrip("/")
        requests.post(
            f"{server}/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": "high",
                "Tags": "tennis,tickets",
                "Click": url,
                "Actions": f"view, Buy now, {url}",
            },
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

    def _webhook(self, title: str, body: str, listing: Listing) -> None:
        cfg = self.config.extra["webhook"]
        if not cfg["url"]:
            log.warning("webhook channel active but WEBHOOK_URL is empty; skipping")
            return
        # A shape that works for both Slack ("text") and Discord ("content").
        payload = {
            "text": f"{title}\n{body}\n{listing.url}",
            "content": f"{title}\n{body}\n{listing.url}",
        }
        requests.post(
            cfg["url"],
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self.config.request_timeout,
        ).raise_for_status()
