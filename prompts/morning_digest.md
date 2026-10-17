# Routine: morning digest

Runs at `morning_digest.time` on `morning_digest.days`.

For each kid:
1. List today's events on every calendar in `calendar.ids`.
2. Keep events for that kid with `kidsbot.rules.events_for_kid` (title mentions their name, or carries an everyone tag).
3. Add today's chores from `kidsbot.rules.chores_for_kid`.
4. Write a cheerful rundown in their age band (see `prompts/kid_persona.md`) and send it on their channel.
5. Nothing on the calendar: send a short good-morning text with that day's chores.
