"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .monitor import Monitor


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ticketbot",
        description="Monitor ticket marketplaces for matching US Open tickets.",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("--once", action="store_true", help="run a single poll cycle and exit")
    parser.add_argument("--test-notify", action="store_true", help="send a test alert and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    monitor = Monitor(config)

    if args.test_notify:
        from datetime import datetime
        from .models import ASHE, Listing

        demo = Listing(
            source="test",
            event_title="US Open Tennis — Arthur Ashe Stadium (Day)",
            price=249.0,
            url="https://www.usopen.org",
            event_datetime=datetime.combine(config.criteria.target_date, datetime.min.time()).replace(hour=12),
            category=ASHE,
            section="Promenade",
            quantity=2,
        )
        monitor.notifier.notify(demo)
        print("Sent a test notification.")
        return 0

    if args.once:
        matched = monitor.poll_once()
        print(f"Done. {len(matched)} new matching listing(s).")
        return 0

    try:
        monitor.run_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
