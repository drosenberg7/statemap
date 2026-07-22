#!/usr/bin/env python3
"""Convenience launcher: `python run.py [--once|--test-notify|-v]`."""

from ticketbot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
