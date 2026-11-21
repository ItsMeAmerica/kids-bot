# kids-bot

A family texting bot. Each kid texts one number and gets age-appropriate help; the parent sets the rules.

- **Homework help** that tutors instead of handing over answers
- **Morning reminders** with each kid's events from the family Google Calendar
- **Chore reminders** with "done" check-offs and a weekly recap for the parent
- **Parent controls**: allowlist, quiet hours, daily caps, pause, transcripts, safety alerts

The full design lives in the plan doc: https://claude.ai/code/artifact/3533f6da-c909-48c8-90a0-35766d8ba148

## How it runs

Version 1 runs as Claude routines that use the Inkbox (texting) and Google Calendar connectors, so there is no server to host:

| Routine | Trigger | Prompt |
| --- | --- | --- |
| Answer texts | Incoming Inkbox iMessage/SMS | `prompts/answer_texts.md` |
| Morning digest | 7:00 am on school days | `prompts/morning_digest.md` |
| Chore reminders | Hourly, 7 am to 8 pm | `prompts/chore_reminders.md` |
| Weekly recap | Sunday 6:00 pm | `prompts/weekly_recap.md` |

Every routine loads `config/family.yaml` and follows `prompts/kid_persona.md`.

The `kidsbot/` Python package holds the logic that must be exact (who is texting, quiet hours, caps, which chores are due, which calendar events belong to which kid) so it can be tested.

Routines can't check more often than once an hour, so for replies within seconds the bot also runs as an always-on service on a home server (see **Instant replies** below). While it runs, it answers texts and the routines only need to do the morning digest, chore reminders and weekly recap.

## Instant replies

Routines check at most once an hour. For replies in a few seconds, run the bot as an always-on service. Inkbox sends each new text to it the moment it arrives (a webhook), it asks Claude (Haiku by default, which answers a short text in a second or two), and texts back.

It applies the same rules as the routines: allowlist, pause, daily cap, quiet hours, "done", test mode, and `prompts/kid_persona.md` with the last few messages. Safety alerts go to the parent right away, even in quiet hours. Each text is answered once, so the hourly routine can keep running as a backup; it skips texts the bot already answered.

Parent texts to the bot:

| Text | Does |
| --- | --- |
| `as <Kid>: <message>` | Test mode only: pretend to be that kid; the reply comes back labeled `[Test for <Kid>]` |
| `pause <Kid>` / `resume <Kid>` | Stop or restart replies to a kid |
| `status` | Replies sent today per kid, and test or live mode |

### Home server with Docker (recommended)

Runs on any always-on Linux box with Docker. No router changes: the bot opens the Inkbox identity's built-in tunnel, so Inkbox can reach it from the internet.

1. On the server: `git clone https://github.com/ItsMeAmerica/kids-bot && cd kids-bot`
2. Real family settings: copy your private `family.yaml` to `config/family.local.yaml` (git-ignored, mounted read-only).
3. Keys: `cp .env.example .env`, then fill in `ANTHROPIC_API_KEY` (from console.anthropic.com, API keys) and `INKBOX_API_KEY` (from the Inkbox console).
4. Tell Inkbox where to send texts (one time):

   ```
   docker compose run --rm kidsbot python -m kidsbot.inkbox_setup
   ```

   It prints `INKBOX_SIGNING_KEY=...` once; paste that line into `.env`. If it says the identity already had a key and you don't have it, run it again with `--new-signing-key`.
5. Start it: `docker compose up -d --build`. Check with `docker compose logs -f`; you should see `inkbox tunnel: connected` and the public address.
6. Text `status` to the bot. A reply within a few seconds means it's working.

It restarts on its own after a reboot or crash. Update with `git pull && docker compose up -d --build`. Settings: `KIDSBOT_MODEL` (default `claude-haiku-5-5`; `claude-sonnet-5-5` is more careful but slower), `INKBOX_HANDLE` (default `bigbrain`). State (where it left off, who is paused, today's counts) lives in `./state/`.

Cost: Claude API usage is billed per text. With Haiku a typical reply costs a small fraction of a cent.

Without Docker: `pip install -r requirements.txt`, export the same variables plus `KIDSBOT_TUNNEL=1`, and run `python -m kidsbot.server`. To use your own public address instead of the Inkbox tunnel (a reverse proxy, Cloudflare Tunnel, or a cloud host), leave `KIDSBOT_TUNNEL` off, expose port 8080 at that address, and run `python -m kidsbot.inkbox_setup https://your-address`. On a cloud host where a file is awkward, `KIDSBOT_CONFIG_YAML` can hold the whole config as text.

### Fallback: check every 15 seconds from your own computer

`python -m kidsbot.poll` needs no public address or signing key. It checks Inkbox every 15 seconds (`KIDSBOT_POLL_SECONDS`) and replies with Claude Code on that computer (your Claude plan, no API key), or the API if `ANTHROPIC_API_KEY` is set. It only answers while that computer is on and awake. Don't run it at the same time as the server.

## Setup

1. Copy `config/family.yaml` to `config/family.local.yaml` (git-ignored) and fill in the real kids, phones and calendars. Real names and numbers never go in the repo. Add chores to the calendar as `Chore: <Kid> - <task>` events.
2. Kids on iPhone text `connect @bigbrain` to the Inkbox iMessage number once. Android kids need a phone number added in Inkbox first.
3. `pip install -r requirements.txt && pytest` to check the config.

## Test mode

`test_mode: true` in `config/family.yaml` sends every kid's message to the parent instead, labeled `[Test for <Kid>]`. Set it to `false` to go live.

## Layout

```
config/family.yaml      family settings (placeholders until filled in)
prompts/                routine and persona prompts
kidsbot/                config loading, rules, and instant replies (server.py webhook, poll.py fallback, inkbox_setup.py)
docker-compose.yml      always-on home server
tests/
```
