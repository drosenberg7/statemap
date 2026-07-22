"""Orchestration: poll every provider, filter, de-dupe, notify."""

from __future__ import annotations

import logging
import random
import time
from typing import List

from .config import Config
from .matcher import match
from .models import Listing
from .notifier import Notifier
from .providers import build_providers
from .state import SeenState

log = logging.getLogger("ticketbot.monitor")


class Monitor:
    def __init__(self, config: Config):
        self.config = config
        self.providers = build_providers(config)
        self.notifier = Notifier(config)
        self.state = SeenState(config.state_path)

    def poll_once(self) -> List[Listing]:
        """Run one full cycle. Returns the listings we newly notified on."""
        criteria = self.config.criteria
        matched: List[Listing] = []

        all_listings: List[Listing] = []
        for provider in self.providers:
            all_listings.extend(provider.fetch())

        log.info("collected %d listing(s) across providers", len(all_listings))

        for listing in all_listings:
            result = match(listing, criteria)
            if not result.ok:
                log.debug("skip %s: %s", listing.summary(), result.reason)
                continue
            if not self.state.should_notify(listing.id, listing.price):
                log.debug("already notified %s", listing.summary())
                continue
            log.info("MATCH %s", listing.summary())
            self.notifier.notify(listing)
            self.state.record(listing.id, listing.price)
            matched.append(listing)

        return matched

    def run_forever(self) -> None:
        interval = self.config.poll_interval_seconds
        crit = self.config.criteria
        log.info(
            "watching %s %s session, categories=%s, under $%.0f, every %ds",
            crit.target_date, crit.session, crit.categories, crit.max_price, interval,
        )
        while True:
            start = time.time()
            try:
                self.poll_once()
            except Exception as exc:  # noqa: BLE001 - keep the loop alive no matter what
                log.exception("poll cycle errored: %s", exc)
            elapsed = time.time() - start
            jitter = random.uniform(0, max(0, self.config.poll_jitter_seconds))
            sleep_for = max(0, interval - elapsed) + jitter
            log.info("cycle done in %.1fs; sleeping %.0fs", elapsed, sleep_for)
            time.sleep(sleep_for)
