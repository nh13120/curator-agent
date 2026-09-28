---
name: status
description: Report Curator's upcoming bookings and open questions on Telegram (the /status command).
disable-model-invocation: true
allowed-tools: Bash(python3 tools/bookings.py *), Bash(python3 tools/pending.py *), Bash(python3 tools/telegram.py *), Bash(python3 tools/clock.py *), Read
---

# /status

Now: !`python3 tools/clock.py context`

Upcoming bookings:

!`python3 tools/bookings.py upcoming`

Open questions waiting on Nicolas:

!`python3 tools/pending.py list --status open`

Write one short Telegram message (`python3 tools/telegram.py send --kind status --text "..."`):

- One line per upcoming booking: weekday and date, time, title, venue, registration state (say "on your calendar" when `calendar_event_id` is set).
- Then "Waiting on you:" with one numbered line per open question (its `id` in parentheses), or "Nothing waiting on you."
- If there are no bookings at all, say so and name the week the next weekly run will plan.

Do not book, cancel or change anything from this skill.
