---
name: plan-week
description: Curator's weekly run. Plans the target week (first Monday at least 4 weeks out) and re-scans the weeks in between; books the best free AI and art events, updates the calendar, reports on Telegram. Follows the procedures in CLAUDE.md.
argument-hint: [optional Monday date to plan instead of the computed horizon]
disable-model-invocation: true
allowed-tools: Bash(python3 tools/*), Agent(scout), Agent(verifier), mcp__playwright__*, Read
---

# /plan-week

Context (computed now):

!`python3 tools/clock.py context`

!`python3 tools/rules.py show`

Arguments: `$ARGUMENTS` (a Monday date narrows the run to that week).

## Procedure

Follow CLAUDE.md exactly. In order:

1. **Start the trace**: `python3 tools/trace.py start --kind weekly --goal "Plan weeks <list>: 1 AI + 1 art event each, free, verified, on the calendar"`. Then `trace.py append --section plan` with your plan in 3–6 bullets.
2. **Read the week brief**: `python3 tools/week.py brief` (add `--week <monday>` when the arguments name a week). One call gives the calendar entries of every selected calendar, the blocked evenings, the current slot status per week, the exclusions and sources per category, and `busy_for_scouts`. Use `gcal.py list` or `deadlines.py` only to look closer at something the brief shows. Derive Nicolas's location per day and the travel days (CLAUDE.md "Where Nicolas is"). Record a `decision` entry with the location JSON you will use. Ambiguous days: escalate per CLAUDE.md and mark them pending.
3. **Decide each slot** (each week × each category from the rules): if already `booked`, note it (swap check happens after scouting). If the calendar already holds a qualifying one-off event of that category, `bookings.py skip` with the reason and a `decision` entry. Otherwise the slot is open.
4. **Scout** open slots: one scout per category per city, all launched in one message; give each its `sources`, `exclusions` and `busy` from the brief (add the travel days and days out of town to `busy`). Then `candidates.py intake`, the verifiers (in one message), and `candidates.py finish` per category (CLAUDE.md "The team"). Retry a scout at most `budgets.scout_retries_per_category` times when `retry_needed` is true; then `bookings.py skip --reason "candidates exhausted: ..."`.
5. **Book** each slot's pick with the CLAUDE.md "Booking procedure" (autonomy tier gate, registration state, backups, calendar, Telegram "Booked" message). Never book something mediocre to fill a quota: a pick that only survives because everything better was removed is still the best available and may be booked; a category with no eligible candidate is skipped.
6. **Swaps**: for slots already booked, if a verified, eligible candidate has a strictly higher speaker tier and the current booking starts more than `swaps.min_days_ahead` days from now, run the CLAUDE.md "Cancellation procedure" for the old booking and book the new one. Otherwise leave it.
7. **Weekly summary** on Telegram (CLAUDE.md "Telegram messages"): bookings made, categories skipped and why, anything ambiguous or waiting on Nicolas.
8. **Stop**: `python3 tools/runs.py record --kind weekly --stop-reason <reason> --summary "..."` and `python3 tools/trace.py stop --reason <reason> --text "..."`. Reasons: `all_slots_resolved` (every slot booked, skipped or pending), `candidates_exhausted`, `budget_hit` (a tool call was denied for budget), `tier3_blocker`, `error`.

Write an `evaluate` trace entry after each major step ("did this move the plan forward?") and a `decision` entry for every pick, skip, swap or escalation, with the reason. Finish with a short summary of what you did; the Telegram message is the report Nicolas reads.
