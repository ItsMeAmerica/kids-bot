# Routine: answer texts

Triggered by a new incoming Inkbox iMessage or SMS.

1. Load `config/family.yaml`. Match the sender's number with `kidsbot.rules.who_is_texting`.
   - Unknown number: reply once "This number is for our family only." and alert the parent. Stop.
   - Parent: handle parent commands (see the plan doc's Parent controls table).
2. If the kid is paused, or over their daily cap, reply once with a short note and stop.
3. If it's quiet hours (`kidsbot.rules.in_quiet_hours`), reply "It's late, ask me in the morning!" and save the question. Safety escalations still go out.
4. If the message is "done" or "done <chore>", mark the chore complete and reply "Nice work!".
5. Otherwise answer following `prompts/kid_persona.md`. Calendar questions ("what time is practice?") are answered from Google Calendar.
6. Log the exchange for the parent's daily transcript. Never send twice for the same incoming message.
