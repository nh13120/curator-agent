---
name: daily-check
description: Curator's daily run. Processes Telegram replies (ratings, answers, rule changes, commands), registers picks whose registration just opened, sends rating prompts and reminders, and re-checks upcoming bookings for new conflicts. Follows CLAUDE.md.
disable-model-invocation: true
allowed-tools: Bash(python3 tools/*), mcp__playwright__*, Read
---

# /daily-check

Context (computed now):

!`python3 tools/clock.py context`

Weekly plan status: !`python3 tools/runs.py stale --kind weekly --days 7 || true`

New Telegram messages (not yet acknowledged):

!`python3 tools/telegram.py get_updates`

Open questions:

!`python3 tools/pending.py list --status open`

Due today:

!`python3 tools/bookings.py due --kind registration`

!`python3 tools/bookings.py due --kind rating`

!`python3 tools/bookings.py due --kind reminder`

Upcoming bookings:

!`python3 tools/bookings.py upcoming`

## Procedure

1. `python3 tools/trace.py start --kind daily --goal "Daily check: process replies, register opened picks, rating prompts, conflict re-check"`, then a `plan` entry.
2. **If the weekly plan is stale** (`stale: true`), say so in the summary; the launcher runs `/plan-week` first, so do not attempt it here.
3. **Process each Telegram message**, oldest first, and record a `decision` per message:
   - `/rules` → send the output of `python3 tools/rules.py show` (kind `status`). `/status` → send upcoming bookings and open questions (kind `status`).
   - A reply to a rating prompt (a number 1–5, optionally with a note, or "didn't go" / "skipped"): find the pending item of kind `rating` it answers (reply-to id, or the most recent open rating prompt). Rating → `python3 tools/memory.py rate --event-id <id> --rating <n> --note "<note>"` and `bookings.py mark --field rated_at --value now`; "didn't go" → `memory.py status --event-id <id> --status skipped`. Close the pending item. Confirm in one line.
   - An answer to a numbered question: `pending.py answer --id <id> --answer "<text>"`, then act on it (for example option "book it" → run the CLAUDE.md "Booking procedure" for that slot; "skip" → `bookings.py skip`). If a required form field was answered, offer to save it: ask "Save this answer for next time? (yes/no)" only once.
   - A free-text rule change → apply the `/rules` mapping (one concrete `rules.py` change, or a question if ambiguous) and reply with exactly what changed.
   - Anything else → answer briefly or ask what they meant; never guess at a rule change.
   After processing, `python3 tools/telegram.py ack --through <highest update_id>`.
4. **Registration re-check**: for each item in `due --kind registration`, fetch the event page; if registration is now open, run the Booking procedure; if it is full, `bookings.py promote-backup --reason full` and book the backup; otherwise leave it.
5. **Rating prompts**: for each item in `due --kind rating`, send "Did you go to <title> (<date>)? Rate it 1–5, and add a note if you want. Reply 'didn't go' if not." (kind `rating`), add a pending item of kind `rating` with the event id, and `bookings.py mark --field rating_prompt_sent_at --value now`. For `due --kind reminder`: action `send_reminder` → send one reminder and `mark --field rating_reminder_sent_at --value now`; action `mark_unconfirmed` → `memory.py status --status unconfirmed`, `mark --field rated_at --value now`, close the pending item.
6. **Conflict re-check** for every upcoming booking: `gcal.py free-check` with the stored travel time, `deadlines.py blocked-evenings` for its date, and the location per day. A new conflict → CLAUDE.md "Cancellation procedure", then book the backup if there is one.
7. Send a short daily summary only if something happened (a booking, a cancellation, a question, a rule change); a quiet day sends nothing.
8. `python3 tools/runs.py record --kind daily --stop-reason <reason>` and `python3 tools/trace.py stop --reason <reason> --text "..."` (`nothing_due` when there was nothing to do).
