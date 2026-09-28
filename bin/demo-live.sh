#!/bin/bash
# Demo on REAL websites. Same agent as production, one week. Each take gets its
# own run id (so the tool-call budget counts only that take) but writes the same
# trace file, so the trace can be open in VS Code before the run starts.
# A dry preview starts from a fresh copy of the live state and memory, so it
# shows what the live take would do.
#
#   bin/demo-live.sh dry  2026-10-05   # preview: real sources + real calendar, no writes (~15 min)
#   bin/demo-live.sh live 2026-10-05   # the take: registers for real, writes the calendar, messages Telegram
#   bin/demo-live.sh live 2026-10-05 luma-boston   # optional: restrict the scouts to these source ids
#
# Trace: dry -> dryrun/logs/runs/demo-dry.md     live -> logs/runs/demo-live.md
# Run bin/demo-cues.sh <dry|live> in a second terminal tab for the recording cues.
set -u
cd "$(dirname "$0")/.." || exit 1
MODE=${1:?usage: demo-live.sh dry|live <monday> [source-ids]}; MONDAY=${2:?usage: demo-live.sh dry|live <monday> [source-ids]}
SOURCES=${3:-}; [ -n "$SOURCES" ] && export CURATOR_SOURCE_IDS="$SOURCES"
case "$MODE" in dry|live) ;; *) echo "mode must be dry or live"; exit 1;; esac
LOCK="/tmp/curator-demo.lock"
if ! mkdir "$LOCK" 2>/dev/null; then echo "another demo run is active (lock $LOCK). Wait for it, or remove the lock if it is stale."; exit 1; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
if pgrep -f "curator/chrome-profile" >/dev/null; then echo "A Chrome window is using Curator's profile (bin/browser-login.sh?). Quit it first."; exit 1; fi
STATE="$(pwd)"; [ "$MODE" = dry ] && STATE="$(pwd)/dryrun"
if [ "$MODE" = dry ]; then
  rm -rf "$STATE/state" "$STATE/memory"; mkdir -p "$STATE/state" "$STATE/memory"
  for f in bookings.json pending.json geocache.json last_runs.json; do [ -f "state/$f" ] && cp "state/$f" "$STATE/state/"; done
  cp memory/*.jsonl memory/*.md "$STATE/memory/" 2>/dev/null
fi
mkdir -p "$STATE/logs/runs"
export CURATOR_TRACE_NAME="demo-$MODE"
rm -f "$STATE/logs/runs/demo-$MODE.jsonl"
printf '# Run demo-%s\n\nWaiting for the run to start…\n' "$MODE" > "$STATE/logs/runs/demo-$MODE.md"
echo "Curator demo ($MODE): week of $MONDAY on real sources and your real calendar.${SOURCES:+ Sources restricted to: $SOURCES}"
echo "Trace: $STATE/logs/runs/demo-$MODE.md"
CURATOR_RUN_ID="demo-$MODE-$(date +%H%M%S)" bin/run.sh weekly --mode "$MODE" "$MONDAY"
RC=$?
echo; echo "Bookings for the week of $MONDAY:"
CURATOR_MODE=$MODE CURATOR_STATE_DIR="$STATE" ./.venv/bin/python tools/bookings.py get --week "$MONDAY" | ./.venv/bin/python -c "
import json,sys; d=json.load(sys.stdin)
for cat, r in d['bookings'].items(): print(f\"  {cat}: {r['status']} — {(r['pick'] or {}).get('title','')} {(r['pick'] or {}).get('start','')[:16]} | registration {r['registration']['state']} | calendar {r['calendar_event_id']}\")"
exit $RC
