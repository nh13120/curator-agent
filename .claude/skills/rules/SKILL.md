---
name: rules
description: Show Curator's current rules, or apply a rule change Nicolas asked for (from Telegram or chat) with a logged diff. Ask instead of guessing when the request is ambiguous.
argument-hint: [free-text rule change, or empty to show the rules]
disable-model-invocation: true
allowed-tools: Bash(python3 tools/rules.py *), Bash(python3 tools/telegram.py *), Bash(python3 tools/pending.py *), Bash(python3 tools/trace.py *), Read
---

# /rules

Current rules (source of truth is `config/rules.yaml`):

!`python3 tools/rules.py show`

Request from Nicolas: `$ARGUMENTS`

## If the request is empty

Send the text above to Telegram with `python3 tools/telegram.py send --kind status --text "<the rules text>"` and stop.

## If there is a request

1. Map it to exactly one of these concrete changes. Do not invent other kinds of changes.
   - A limit or switch: `python3 tools/rules.py set --path <dotted.path> --value <yaml> --request "<original text>" --source telegram`
     (examples: `max_travel_min`, `evening_cutoff`, `categories.0.per_week`, `swaps.min_days_ahead`, `in_person_only`)
   - Avoid a topic, speaker or venue: `python3 tools/rules.py exclude --kind topics|speakers|venues --value "<term>" --request "..." --source telegram`
   - A new category: `python3 tools/rules.py add-category --id <id> --label "<Label>" --per-week 1 --every-n-weeks <n> --description "..." --request "..." --source telegram`
     ("every other week" means `--every-n-weeks 2`)
   - Drop a category: `python3 tools/rules.py remove-category --id <id> --request "..." --source telegram`
   - Turn a category off without deleting it: `set --path categories.<i>.per_week --value 0`
2. The tool refuses changes to the free-only guardrail. Never work around that.
3. If the request could mean two different changes (for example "less art" could be per_week 0 or a topic exclusion), do not apply anything. Record a question with `python3 tools/pending.py add --kind rule_change --question "..." --options "1) ...|2) ..."`, send it with `python3 tools/telegram.py send --kind question --text "..."`, and stop.
4. After a successful change, reply on Telegram with exactly what changed, quoting the `changes` list (path, old → new). Keep it short.
5. Every change is logged automatically to `memory/rules_history.jsonl` with a unified diff; do not edit `config/rules.yaml` by hand.
