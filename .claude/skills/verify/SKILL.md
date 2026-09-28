---
name: verify
description: How to verify a Curator change at its real surfaces (launcher, tools, schedules) without running the eval or tests. Developer recipe, not part of the product.
disable-model-invocation: true
allowed-tools: Bash(python3 tools/*), Bash(bin/*), Bash(launchctl print *), Read
---

# Verifying Curator changes

Every surface is a CLI. Drive it, capture the JSON, never import tools in Python.

## Handles

- Tools: `CURATOR_MODE=dry python3 tools/<name>.py <verb> ...` reads the REAL calendar, ledger and web but blocks writes (calendar `create`, telegram `send` is prefixed). Use `CURATOR_MODE=fixture CURATOR_CASE=<case> CURATOR_STATE_DIR=<scratch dir>` for offline runs against `fixtures/cases/<case>/`.
- Launcher: `bin/run.sh daily --mode dry` (about 3 min, ~$0.70 est., sends `[DRY RUN]` Telegram messages; state goes to `dryrun/`). `bin/run.sh weekly --mode dry 2026-10-26` narrows to one week (~15–20 min). Live mode books for real: do not use it to verify.
- Schedules: `bin/schedule.sh status`, then `launchctl print gui/$(id -u)/com.nicolash.curator.daily | grep -A3 arguments` to see the path launchd really holds. Never `run-now` while verifying: it is a live run.
- Ranker: write a small candidates JSON (see `tools/rank.py` selftest for the shape) and run `rank.py rank --candidates <file> --week <monday> --location-json - <<< '{...}'` in fixture mode; read `ranked[].eligible` and `ineligible_reasons`.
- Classifier: `CURATOR_MODE=dry python3 tools/rsvp.py classify-form --url <real registration url>` uses `config/profile.yaml`.

## Gotchas found so far

- The project path contains `&`: never use sed substitution on it (`schedule.sh` fills plists with python for that reason); never source `.env` in bash.
- Skill dynamic-context lines must not exit non-zero (`|| true`), or the skill runs zero turns.
- A dry run before 2026-09-27 wrote into the live `state/`; now `bin/run.sh --mode dry` uses `dryrun/`.
- Live state check: `md5 -q state/bookings.json state/pending.json state/telegram_offset.json memory/history.jsonl` before and after a dry run must match.
- Selftests get a throwaway state folder automatically when `CURATOR_STATE_DIR` is unset (`_common.py`, since 2026-09-27; before that `pending` and `trace` selftests wrote into the live state). Check: live `state/` checksums and the `logs/runs` file count unchanged after a selftest loop.
- Dry runs ask Telegram for updates from the LIVE offset (`state/telegram_offset.json`); their own offset in `dryrun/` only hides messages they already answered (since 2026-09-27; before that a second dry run could delete unread replies server-side). Check: `CURATOR_MODE=dry CURATOR_STATE_DIR=dryrun python3 tools/telegram.py get_updates` shows `server_offset_from` equal to the live `through`.
- Default `fetch.py` output is a frozen contract (the baseline uses it). Check it byte-for-byte against the previous commit from a `git worktree` of that commit, run with the project's `.venv/bin/python`.
