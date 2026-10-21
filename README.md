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

Routines can't check more often than once an hour, so for replies within seconds there is also a small always-on server (see **Instant replies** below). When it's running, it answers texts and the routines only do the morning digest, chore reminders and weekly recap.

## Instant replies

`python -m kidsbot.server` listens at `POST /webhooks/inkbox`. Inkbox calls it the moment a kid texts; it checks the signature, applies the same rules (allowlist, pause, daily cap, quiet hours, "done", test mode), asks Claude for a reply using `prompts/kid_persona.md` and the last few messages, and texts back. Safety alerts go to the parent right away, even in quiet hours. Each incoming text is answered once, even if Inkbox retries.

Parent texts to the bot:

| Text | Does |
| --- | --- |
| `as <Kid>: <message>` | Test mode only: pretend to be that kid; the reply comes back labeled `[Test for <Kid>]` |
| `pause <Kid>` / `resume <Kid>` | Stop or restart replies to a kid |
| `status` | Replies sent today per kid, and test or live mode |

### Setup

You need:

- An **Anthropic API key** from https://console.anthropic.com (pay as you go).
- An **Inkbox API key** from the Inkbox console.
- A **host** that runs a Docker container all the time with an `https://` address, for example Render, Railway or Fly.io. The `Dockerfile` here works on any of them.

Steps:

1. Deploy this repo to the host and set these environment variables (in the host's settings, never in the repo):

   | Variable | Value |
   | --- | --- |
   | `ANTHROPIC_API_KEY` | your Anthropic key |
   | `INKBOX_API_KEY` | your Inkbox key |
   | `INKBOX_SIGNING_KEY` | from step 2 |
   | `KIDSBOT_CONFIG_YAML` | the full text of your real `family.local.yaml` |
   | `INKBOX_HANDLE` | optional, defaults to `bigbrain` |
   | `KIDSBOT_MODEL` | optional, defaults to `claude-opus-5-5`; `claude-haiku-5-5` is cheaper |

2. Register the webhook once, from any computer with this repo:

   ```
   pip install -r requirements.txt
   INKBOX_API_KEY=... python scripts/register_webhook.py https://<your-host-address>
   ```

   It prints the signing key once. Put it in `INKBOX_SIGNING_KEY` on the host and restart.
3. Text `status` to the bot. A reply means it's working. Then turn off the "answer texts" part of the hourly routine so kids don't get two answers.

The server keeps a small file at `state/server.json` (who is paused, today's counts). If the host wipes it on restart, counts start over and paused kids need pausing again.

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
kidsbot/                config loading, rules, and the instant-replies server
scripts/                one-time webhook registration
tests/
```
