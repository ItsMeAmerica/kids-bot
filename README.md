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

The `kidsbot/` Python package holds the logic that must be exact (who is texting, quiet hours, caps, which chores are due, which calendar events belong to which kid) so it can be tested, and later used by a standalone server if the family outgrows routines.

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
kidsbot/                config loading and rules, with tests
tests/
```
