#!/bin/bash
# Install, inspect or remove Curator's launchd schedules.
#
#   bin/schedule.sh install     # weekly Saturday 08:00, daily 07:30 (live mode)
#   bin/schedule.sh status
#   bin/schedule.sh run-now weekly|daily     # trigger one run through launchd
#   bin/schedule.sh remove
#
# If the Mac is asleep at the scheduled time, launchd runs the job on wake.
# If it was shut down, the daily job performs the missed weekly plan (bin/run.sh).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
PROJECT="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS="com.nicolash.curator.weekly com.nicolash.curator.daily"
UID_=$(id -u)

case "${1:-}" in
  install)
    mkdir -p "$AGENTS" "$HOME/Library/Logs/curator"
    for L in $LABELS; do
      # Fill placeholders with python: the project path contains "&", which sed treats specially.
      ./.venv/bin/python -c "import sys,pathlib; t=pathlib.Path(sys.argv[1]).read_text(); pathlib.Path(sys.argv[2]).write_text(t.replace('__PROJECT__', sys.argv[3]).replace('__HOME__', sys.argv[4]))" "launchd/$L.plist" "$AGENTS/$L.plist" "$PROJECT" "$HOME"
      launchctl bootout "gui/$UID_/$L" 2>/dev/null || true
      launchctl bootstrap "gui/$UID_" "$AGENTS/$L.plist"
      echo "installed $L"
    done ;;
  status)
    for L in $LABELS; do
      if launchctl print "gui/$UID_/$L" >/dev/null 2>&1; then
        echo "$L: loaded"; launchctl print "gui/$UID_/$L" | grep -E "state|last exit|run interval|program" | head -6
      else echo "$L: not loaded"; fi
    done
    echo "logs: $HOME/Library/Logs/curator/" ;;
  run-now)
    K=${2:?weekly|daily}; launchctl kickstart -k "gui/$UID_/com.nicolash.curator.$K"; echo "kicked $K" ;;
  remove)
    for L in $LABELS; do launchctl bootout "gui/$UID_/$L" 2>/dev/null || true; rm -f "$AGENTS/$L.plist"; echo "removed $L"; done ;;
  *) echo "usage: schedule.sh install|status|run-now weekly|daily|remove"; exit 1 ;;
esac
