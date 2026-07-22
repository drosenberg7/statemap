# US Open Ticket Monitor 🎾

A bot that watches multiple ticket marketplaces (TickPick, SeatGeek,
Ticketmaster, Vivid Seats, StubHub) and sends you a **push notification** the
moment a US Open ticket appears that matches what you're hunting for.

Out of the box it's configured for the request it was built for:

> **Aug 30, 2026 · day session · Grounds Pass, Arthur Ashe Stadium, or Louis
> Armstrong Stadium · under $275.**

All of that is configurable in `config.yaml`.

---

## How it works

Every few minutes the bot:

1. **Polls each marketplace** through a pluggable *provider* (`ticketbot/providers/`).
2. **Normalizes** every offer into a common `Listing` shape.
3. **Filters** on your criteria — date, day/night session, venue/category, and a
   strict price ceiling (`ticketbot/matcher.py`).
4. **De-dupes** against a small on-disk state map so you're alerted once per
   listing, and again only if the price *drops* (`state.json`, hence the repo
   name — a *map of state*).
5. **Notifies** you via [ntfy.sh](https://ntfy.sh) push (plus optional email /
   Discord / Slack).

Everything is defensive: if one marketplace changes its markup, blocks a
request, or times out, that provider logs a warning and returns nothing — the
other providers and the loop keep running.

---

## Quick start

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Set up push notifications (free, no account)
#    - Install the "ntfy" app on your phone (iOS/Android)
#    - Subscribe to a topic, e.g.  usopen-tickets-your-random-suffix
cp .env.example .env
#    edit .env and set NTFY_TOPIC to that SAME topic name

# 3. Load env + do a test push (should hit your phone)
set -a; source .env; set +a
python run.py --test-notify

# 4. Run one poll cycle to sanity-check
python run.py --once

# 5. Run it for real (loops forever)
python run.py
```

> ⚠️ Pick a **long, random** ntfy topic name. Anyone who knows the topic can
> read your alerts, and anyone can publish to it. Treat it like a password.

---

## Configuration (`config.yaml`)

```yaml
criteria:
  target_date: 2026-08-30   # session date (YYYY-MM-DD)
  session: day              # day | night | any
  categories: [grounds, ashe, armstrong]
  max_price: 275            # alert only strictly BELOW this (USD)

providers: [tickpick, seatgeek, ticketmaster]
poll_interval_seconds: 300  # 5 min — don't set this too low
notify:
  channels: [ntfy, console]
```

Secrets and marketplace ids live in the environment (`.env`), never in the yaml
file. See `.env.example` for every supported variable.

### A note on prices & fees

The price ceiling is compared against whatever number a marketplace reports:

- **TickPick** prices are **all-in** (no checkout fees) — a match under $275
  really is under $275. Best signal for a hard budget.
- **SeatGeek / Ticketmaster / Vivid Seats** usually report **pre-fee** prices,
  so a $250 match can land around $290 after fees. If you want the *final*
  price under $275, set `max_price` a bit lower (≈ `275 / 1.15 ≈ 240`) for those,
  or lean on TickPick.

---

## Reliability: scraping vs. official APIs

You chose **scrape-only** (no API keys), so the bot uses best-effort public
endpoints by default. Be aware:

- Ticket sites deploy bot protection (Cloudflare/PerimeterX) and change their
  internal JSON endpoints without notice. Scraping **will** occasionally break;
  when it does, the fix is usually a small change to one provider's endpoint or
  parsing in `ticketbot/providers/`.
- The parsing logic for every provider is a **pure function** with unit tests
  (`tests/test_providers.py`), so when a payload shape changes you can capture
  the new JSON, update the parser, and re-run the tests.

**Want maximum reliability?** Two zero-cost upgrades, both already supported:

- **Ticketmaster**: get a free key at
  <https://developer.ticketmaster.com> → set `TICKETMASTER_API_KEY`. The bot
  then uses the official Discovery API (US Open tickets sell through
  Ticketmaster, so this is the highest-signal source).
- **SeatGeek**: get a free client id at
  <https://seatgeek.com/account/develop> → set `SEATGEEK_CLIENT_ID`. The bot
  switches from HTML scraping to the stable Platform API.

For TickPick/Vivid Seats you can pin exact event ids
(`TICKPICK_EVENT_IDS`, `VIVIDSEATS_PRODUCTION_IDS`) once you've browsed to the
Aug 30 sessions — this sidesteps the fragile search step entirely.

---

## Running it 24/7 (every minute)

The bot is a long-running process that loops on `poll_interval_seconds` (set to
**60** — every minute). It needs an **always-on host**; it won't survive on your
laptop if it sleeps. Two ready-made options:

### Option A — Docker (recommended, auto-restarts)

```bash
cp .env.example .env        # fill in NTFY_TOPIC (+ any API keys)
docker compose up -d        # runs forever, restarts on crash AND host reboot
docker compose logs -f      # watch it
docker compose down         # stop
```

State persists in `./data/state.json` (mounted volume), so restarts don't
re-alert you. Edit `config.yaml` then `docker compose restart` to apply changes.

### Option B — systemd (VPS / Raspberry Pi, no Docker)

```bash
sudo cp deploy/ticketbot.service /etc/systemd/system/
# edit User/WorkingDirectory/EnvironmentFile paths in the unit file
sudo systemctl daemon-reload
sudo systemctl enable --now ticketbot
journalctl -u ticketbot -f
```

Auto-restarts on crash (`Restart=always`) and starts on boot.

### Option C — GitHub Actions (no server of your own)

If you don't have an always-on machine, `.github/workflows/monitor.yml` runs the
bot on GitHub's free scheduled runners. Caveats to set expectations:

- **Every 5 minutes, not every minute** — that's GitHub's minimum, and runs are
  best-effort (delayed/skipped under load).
- Runners use datacenter IPs that ticket sites often block, so this option is
  **really only dependable with the API keys set** (below).
- The schedule only starts firing once the workflow file is on your **default
  branch (`main`)**.

De-dup state is persisted between runs via the Actions cache, so you won't get
repeat alerts.

> **Heads-up on "every minute":** polling scrape endpoints 1,440×/day per site
> is aggressive and will likely get your IP rate-limited or blocked. To make
> minute-level polling actually reliable, either (a) add the free
> **Ticketmaster / SeatGeek API keys** (their APIs tolerate frequent polling),
> and/or (b) set `poll_jitter_seconds: 20` so requests aren't perfectly
> periodic. If you start seeing empty results or errors in the logs, back the
> interval off to 120–180s.

---

## Notification channels

`ntfy` push is the default. You can enable more by adding them to
`notify.channels` in `config.yaml` and setting the matching env vars:

| Channel   | Env vars |
|-----------|----------|
| `ntfy`    | `NTFY_TOPIC`, `NTFY_SERVER` |
| `console` | — (prints to stdout) |
| `email`   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` |
| `webhook` | `WEBHOOK_URL` (Discord or Slack incoming webhook) |

---

## Project layout

```
ticketbot/
  config.py        # load/validate config.yaml + env
  models.py        # Listing dataclass + category constants
  matcher.py       # criteria filtering (pure, tested)
  state.py         # persistent de-dup ("statemap")
  notifier.py      # ntfy / console / email / webhook
  monitor.py       # poll → filter → dedupe → notify loop
  cli.py           # `python run.py` entrypoint
  providers/       # one module per marketplace
tests/             # 34 unit + integration tests
```

## Development

```bash
pip install pytest
python -m pytest -q          # run the suite
python run.py --once -v      # one verbose cycle
```

---

## Legal / fair use

This tool is for personal, low-frequency monitoring to help *you* buy a ticket.
Respect each site's Terms of Service and rate limits, don't redistribute their
data, and don't use it to bulk-scalp. If a site offers an official API (they
do — see above), prefer it.
