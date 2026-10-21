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

Routines can't check more often than once an hour, so for replies within seconds the bot can also run on your own computer (see **Instant replies** below). While it runs, it answers texts and the routines only need to do the morning digest, chore reminders and weekly recap.

## Instant replies

Routines check at most once an hour. For replies within seconds, run the bot on your own computer:

```
python -m kidsbot.poll
```

It checks Inkbox for new texts every 15 seconds, applies the same rules (allowlist, pause, daily cap, quiet hours, "done", test mode), writes the reply with Claude Code using `prompts/kid_persona.md` and the last few messages, and texts back. Safety alerts go to the parent right away, even in quiet hours. Each text is answered once.

It costs nothing extra: no host, and replies use the Claude plan Claude Code is signed in with. It only answers while the computer is on and awake; texts sent while it's off get answered by the hourly routine instead.

Parent texts to the bot:

| Text | Does |
| --- | --- |
| `as <Kid>: <message>` | Test mode only: pretend to be that kid; the reply comes back labeled `[Test for <Kid>]` |
| `pause <Kid>` / `resume <Kid>` | Stop or restart replies to a kid |
| `status` | Replies sent today per kid, and test or live mode |

### Setup on your computer

1. Install [Python 3.11+](https://www.python.org/downloads/) and [Claude Code](https://claude.com/claude-code). Run `claude` once and sign in.
2. Download this repo, then in its folder: `pip install -r requirements.txt`
3. Put your real settings in `config/family.local.yaml` (git-ignored; copy `config/family.yaml` and fill it in).
4. Get your Inkbox API key from the Inkbox console and start the bot:

   ```
   export INKBOX_API_KEY=your-key
   caffeinate -i python -m kidsbot.poll     # Mac: keeps it awake while running
   ```

   On Windows use `set INKBOX_API_KEY=your-key` and `python -m kidsbot.poll`.
5. Text `status` to the bot. A reply means it's working. The hourly routine skips texts the bot already answered, so both can run.

Optional settings: `INKBOX_HANDLE` (default `bigbrain`), `KIDSBOT_POLL_SECONDS` (default 15), `KIDSBOT_MODEL` (default: Claude Code's). If `ANTHROPIC_API_KEY` is set, replies use the pay-as-you-go API instead of Claude Code.

The bot keeps a small file at `state/server.json` (where it left off, who is paused, today's counts).

### Optional: always-on host

To answer even when your computer is off, `python -m kidsbot.server` (or the `Dockerfile`) runs the same bot as a webhook at `POST /webhooks/inkbox` on a host such as Render or Railway. That costs a monthly fee and needs `ANTHROPIC_API_KEY`, `INKBOX_API_KEY`, `KIDSBOT_CONFIG_YAML` (the text of your real config) and `INKBOX_SIGNING_KEY`, which `INKBOX_API_KEY=... python scripts/register_webhook.py https://<host>` prints once.

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
kidsbot/                config loading, rules, and instant replies (poll.py local, server.py hosted)
scripts/                one-time webhook registration
tests/
```
