#!/bin/bash
# Recording cues. Run in a SECOND terminal tab while the demo runs:
#   bin/demo-cues.sh            # fixture demo (bin/demo.sh)
#   bin/demo-cues.sh live       # bin/demo-live.sh live ...
#   bin/demo-cues.sh dry        # bin/demo-live.sh dry ...
# Announces out loud and prints: "scouts launched" (take 1 can end), "browser" (record take 2 NOW),
# "booked", "done" (stop recording).
set -u
cd "$(dirname "$0")/.." || exit 1
MODE=${1:-fixture}
case "$MODE" in
  fixture) LOG="demo/logs/tool_calls.jsonl"; RID="demo" ;;
  live)    LOG="logs/tool_calls.jsonl";      RID="demo-live" ;;
  dry)     LOG="dryrun/logs/tool_calls.jsonl"; RID="demo-dry" ;;
  *) echo "usage: demo-cues.sh [fixture|live|dry]"; exit 1 ;;
esac
echo "Waiting for the $MODE demo to start (watching $LOG for run ids starting with $RID)…"
until [ -f "$LOG" ]; do sleep 1; done
cue() { printf '\n\033[1;33m>>> %s  (%s)\033[0m\n\n' "$1" "$(date +%H:%M:%S)"; say -v Samantha "$2" 2>/dev/null & }
scouts=0; browser=0; booked=0
tail -n 0 -F "$LOG" 2>/dev/null | while IFS= read -r line; do
  case "$line" in *"\"run_id\": \"$RID"*) ;; *) continue ;; esac   # prefix: demo-live-<time>
  case "$line" in
    *'"tool_name": "Agent"'*)  scouts=$((scouts+1)); [ $scouts -eq 2 ] && cue "TWO SCOUTS LAUNCHED — take 1 can end here" "scouts launched" ;;
    *'browser_navigate'*)      [ $browser -eq 0 ] && { browser=1; cue "BROWSER OPENED — RECORD TAKE 2 NOW" "browser"; } ;;
    *'bookings.py book'*)      [ $booked -eq 0 ] && { booked=1; cue "BOOKED — confirmation recorded" "booked"; } ;;
    *'trace.py stop'*)         cue "RUN DONE — stop recording" "done"; break ;;
  esac
done
