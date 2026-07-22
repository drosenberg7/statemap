"""Provider base class.

A provider knows how to query one marketplace and return a list of normalized
`Listing` objects for the US Open. Providers must be defensive: marketplaces
change markup/endpoints and deploy bot protection constantly, so a provider
should catch its own errors, log, and return whatever it managed to parse
rather than taking down the whole poll cycle.
"""

from __future__ import annotations

import logging
from typing import List

import requests

from ..config import Config
from ..models import Listing

log = logging.getLogger("ticketbot.providers")


class Provider:
    name: str = "base"

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def fetch(self) -> List[Listing]:
        """Return normalized listings. Subclasses override `_fetch`."""
        try:
            listings = self._fetch()
            log.info("%s: %d raw listing(s)", self.name, len(listings))
            return listings
        except Exception as exc:  # noqa: BLE001 - one bad provider must not kill the run
            log.warning("%s: fetch failed: %s", self.name, exc)
            return []

    def _fetch(self) -> List[Listing]:  # pragma: no cover - abstract
        raise NotImplementedError

    def _get(self, url: str, **kwargs):
        kwargs.setdefault("timeout", self.config.request_timeout)
        return self.session.get(url, **kwargs)
