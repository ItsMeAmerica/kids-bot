# Routine: chore reminders

Runs hourly from 7 am to 8 pm (scheduled tasks run at most hourly).

Chores live on the calendars in `calendar.ids` as events titled `Chore: <Kid> - <task>` (or `Chore: [All] - <task>` for every kid). Use recurring events for repeating chores.

For each kid, use `kidsbot.rules.chores_due` to find chore events that started in the last hour and send one short reminder naming the task (`kidsbot.rules.chore_name`). A chore still not done 2 hours after its start gets one follow-up nudge. Never more than two messages per chore per day. Skip quiet hours.
