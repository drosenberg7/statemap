"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import List

import yaml

from .models import ARMSTRONG, ASHE, GRANDSTAND, GROUNDS


@dataclass
class Criteria:
    """What the user is hunting for."""

    target_date: date            # session date, e.g. 2026-08-30
    session: str                 # "day" | "night" | "any"
    categories: List[str]        # subset of {grounds, ashe, armstrong}
    max_price: float             # notify only strictly below this (USD)


@dataclass
class Config:
    criteria: Criteria
    providers: List[str]         # which providers to poll
    poll_interval_seconds: int
    poll_jitter_seconds: int
    ntfy_topic: str
    ntfy_server: str
    notifiers: List[str]         # active notifier backends
    state_path: str
    tickpick_events: List[dict] = field(default_factory=list)
    request_timeout: int = 20
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    # Secrets / channel settings pulled from the environment, not the yaml file.
    extra: dict = field(default_factory=dict)


_VALID_CATEGORIES = {GROUNDS, ASHE, ARMSTRONG, GRANDSTAND}


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    crit_raw = raw.get("criteria", {})

    target_date = crit_raw.get("target_date")
    if isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    if not isinstance(target_date, date):
        raise ValueError("criteria.target_date must be a YYYY-MM-DD date")

    categories = [c.strip().lower() for c in crit_raw.get("categories", [])]
    bad = set(categories) - _VALID_CATEGORIES
    if bad:
        raise ValueError(
            f"Unknown categories {sorted(bad)}; valid: {sorted(_VALID_CATEGORIES)}"
        )
    if not categories:
        categories = sorted(_VALID_CATEGORIES)

    session = str(crit_raw.get("session", "day")).lower()
    if session not in {"day", "night", "any"}:
        raise ValueError("criteria.session must be day, night, or any")

    max_price = float(crit_raw.get("max_price", 275))

    criteria = Criteria(
        target_date=target_date,
        session=session,
        categories=categories,
        max_price=max_price,
    )

    notify_raw = raw.get("notify", {})
    # Env vars win over yaml for the topic so secrets can stay out of git.
    ntfy_topic = os.environ.get("NTFY_TOPIC", notify_raw.get("ntfy_topic", ""))
    ntfy_server = os.environ.get(
        "NTFY_SERVER", notify_raw.get("ntfy_server", "https://ntfy.sh")
    )
    notifiers = notify_raw.get("channels", ["ntfy", "console"])

    # Optional per-event pins (currently TickPick). Each needs an id; category
    # is validated against the known venues so a typo fails loudly.
    tickpick_events = []
    for ev in raw.get("tickpick_events", []) or []:
        if "id" not in ev:
            raise ValueError("each tickpick_events entry needs an 'id'")
        cat = str(ev.get("category", "")).strip().lower() or None
        if cat is not None and cat not in _VALID_CATEGORIES:
            raise ValueError(f"tickpick_events id={ev['id']}: bad category {cat!r}")
        tickpick_events.append({
            "id": str(ev["id"]),
            "category": cat,
            "label": ev.get("label", "US Open Tennis"),
        })

    extra = {
        "email": {
            "smtp_host": os.environ.get("SMTP_HOST", ""),
            "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
            "smtp_user": os.environ.get("SMTP_USER", ""),
            "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
            "from_addr": os.environ.get("EMAIL_FROM", ""),
            "to_addr": os.environ.get("EMAIL_TO", ""),
        },
        "webhook": {
            "url": os.environ.get("WEBHOOK_URL", ""),
        },
    }

    return Config(
        criteria=criteria,
        providers=raw.get("providers", ["tickpick", "seatgeek", "ticketmaster"]),
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 300)),
        poll_jitter_seconds=int(raw.get("poll_jitter_seconds", 0)),
        ntfy_topic=ntfy_topic,
        ntfy_server=ntfy_server,
        notifiers=notifiers,
        state_path=os.environ.get("STATE_PATH", raw.get("state_path", "state.json")),
        tickpick_events=tickpick_events,
        request_timeout=int(raw.get("request_timeout", 20)),
        extra=extra,
    )
