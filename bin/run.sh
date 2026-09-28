#!/bin/bash
# Curator launcher. Used by launchd and by hand.
#
#   bin/run.sh weekly [--mode live|dry] [<Monday date>]     # weekly plan (Saturday)
#   bin/run.sh daily  [--mode live|dry]                      # daily check (every morning)
#
# Runs Claude Code headless with the skill for the kind of run, in the given
# mode (default: live, or CURATOR_MODE if set). Logs go to ~/Library/Logs/curator/
# because LaunchAgents cannot write under ~/Desktop. A daily run first performs
# a missed weekly plan (older than 7 days) so a sleeping Mac catches up.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KIND=${1:?usage: run.sh weekly|daily [--mode live|dry] [args]}; shift
MODE=${CURATOR_MODE:-live}
if [ "${1:-}" = "--mode" ]; then MODE=$2; shift 2; fi
case "$KIND" in weekly|daily) ;; *) echo "kind must be weekly or daily"; exit 1;; esac
case "$MODE" in live|dry) ;; *) echo "mode must be live or dry (fixture runs go through eval/run_eval.py)"; exit 1;; esac

# .env is read by the tools themselves (python-dotenv in tools/_common.py), so the
# launcher does not source it: shell parsing of an unquoted value could misfire.
# Only the optional model override is read here.
CURATOR_MODEL="${CURATOR_MODEL:-$(./.venv/bin/python -c "from dotenv import dotenv_values; print(dotenv_values('.env').get('CURATOR_MODEL') or '')" 2>/dev/null)}"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# A nested Claude session must not think this is a child of itself.
for v in $(env | grep -oE '^CLAUDE_CODE_[A-Z_]+'); do unset "$v"; done; unset CLAUDECODE

export CURATOR_MODE="$MODE"
# Dry runs keep their state apart so a rehearsal never looks like a real booking.
if [ "$MODE" = dry ]; then export CURATOR_STATE_DIR="$(pwd)/dryrun"; mkdir -p "$CURATOR_STATE_DIR"; else export CURATOR_STATE_DIR="$(pwd)"; fi
export CURATOR_RUN_ID="${CURATOR_RUN_ID:-$(date +%Y%m%d-%H%M%S)-$KIND}"
BUDGET=$(./.venv/bin/python -c "import yaml; print(yaml.safe_load(open('config/rules.yaml'))['budgets']['tool_calls_$KIND'])")
export CURATOR_TOOL_BUDGET="${CURATOR_TOOL_BUDGET:-$BUDGET}"
LOG="$HOME/Library/Logs/curator"; mkdir -p "$LOG"
OUT="$LOG/$CURATOR_RUN_ID.json"; ERR="$LOG/$CURATOR_RUN_ID.err"

# Catch-up: if the weekly plan is stale, do it before the daily check (live only:
# the dry state dir starts empty and would always look stale).
if [ "$KIND" = daily ] && [ "$MODE" = live ] && ./.venv/bin/python tools/runs.py stale --kind weekly --days 7 >/dev/null 2>&1; then
  echo "$(date) weekly plan stale: running it first" >> "$ERR"
  CURATOR_RUN_ID="${CURATOR_RUN_ID%-daily}-weekly-catchup" "$0" weekly --mode "$MODE" || true
fi

if [ "$KIND" = weekly ]; then SKILL="/plan-week"; MAX_TURNS=150; MAX_USD=12; else SKILL="/daily-check"; MAX_TURNS=80; MAX_USD=5; fi
echo "$(date) start $KIND mode=$MODE run=$CURATOR_RUN_ID budget=$CURATOR_TOOL_BUDGET" >> "$ERR"
claude -p "$SKILL${*:+ $*}" \
  --settings "config/modes/$MODE.json" --setting-sources project,local \
  --permission-mode dontAsk --permission-prompts none \
  --max-turns "$MAX_TURNS" --max-budget-usd "$MAX_USD" \
  --model "${CURATOR_MODEL:-claude-opus-5}" \
  --output-format json --no-session-persistence \
  > "$OUT" 2>> "$ERR"
RC=$?
echo "$(date) end $KIND rc=$RC" >> "$ERR"
# One-line summary for the log (the trace itself is in logs/runs/<run id>.md).
./.venv/bin/python - "$OUT" <<'PY' 2>/dev/null
import json, sys
try:
    r = json.load(open(sys.argv[1]))
    print(f"turns={r.get('num_turns')} cost_est=${r.get('total_cost_usd', 0):.2f} error={r.get('is_error')} :: {(r.get('result') or '')[:300]}")
except Exception as e:
    print(f"no result json: {e}")
PY
exit $RC
