#!/bin/bash
# Demo run for the video: fixture case 5 (sold-out top pick + stale listing) with a
# VISIBLE browser, its own state folder (demo/), and a fixed run id so the trace
# file demo/logs/runs/demo.md can be open in VS Code before the run starts.
#
#   bin/demo.sh              # ~6 minutes; nothing real is touched (fixture mode)
#
# What to have on screen: this terminal, VS Code on demo/logs/runs/demo.md,
# and the Chrome window that opens by itself when the agent registers.
set -u
cd "$(dirname "$0")/.." || exit 1
CASE=case5_failure_recovery
DEMO="$(pwd)/demo"
LOCK="/tmp/curator-demo.lock"
if ! mkdir "$LOCK" 2>/dev/null; then echo "another demo run is active (lock $LOCK). Wait for it, or remove the lock if it is stale."; exit 1; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
rm -rf "$DEMO"; mkdir -p "$DEMO/state" "$DEMO/memory" "$DEMO/logs/runs" "$DEMO/logs/screenshots" "$DEMO/screenshots"
cp "fixtures/cases/$CASE/history.jsonl" "fixtures/cases/$CASE/seen.jsonl" "$DEMO/memory/"
echo '{"weeks": {}}' > "$DEMO/state/bookings.json"; echo '{"items": []}' > "$DEMO/state/pending.json"
printf '# Run demo\n\nWaiting for the run to start…\n' > "$DEMO/logs/runs/demo.md"
sed "s#__OUTPUT_DIR__#$DEMO/screenshots#; s#\"--headless\",##" eval/mcp.fixture.template.json > "$DEMO/mcp.json"
TODAY=$(./.venv/bin/python -c "import json; print(json.load(open('fixtures/cases/$CASE/case.json'))['today'])")

pkill -f "fixtures/site/server.py" 2>/dev/null; sleep 0.3
./.venv/bin/python fixtures/site/server.py --case $CASE --port 8765 --out "$DEMO/submissions.jsonl" > "$DEMO/site.log" 2>&1 &
SITE=$!
for i in $(seq 1 20); do curl -sf http://127.0.0.1:8765/health >/dev/null && break; sleep 0.5; done
for v in $(env | grep -oE '^CLAUDE_CODE_[A-Z_]+'); do unset "$v"; done; unset CLAUDECODE
export CURATOR_MODE=fixture CURATOR_CASE=$CASE CURATOR_STATE_DIR="$DEMO" CURATOR_RUN_ID=demo CURATOR_TODAY="$TODAY" \
       CURATOR_SITE_URL=http://127.0.0.1:8765 CURATOR_TOOL_BUDGET=160

echo "Curator demo: fixture case 5 (top pick sold out + stale listing). Frozen today: $TODAY"
echo "Trace: $DEMO/logs/runs/demo.md   Mock site: http://127.0.0.1:8765/"
echo "Starting the weekly plan…"
claude -p "/plan-week" --setting-sources project,local --settings config/modes/fixture.json \
  --mcp-config "$DEMO/mcp.json" --strict-mcp-config \
  --disallowedTools WebSearch WebFetch Workflow SendMessage ListAgents Monitor CronCreate CronDelete RemoteTrigger PushNotification EnterWorktree \
  --permission-mode dontAsk --permission-prompts none --max-turns 150 --max-budget-usd 6 --model claude-opus-5 \
  --output-format json --no-session-persistence > "$DEMO/result.json" 2> "$DEMO/stderr.txt"
RC=$?
kill $SITE 2>/dev/null
./.venv/bin/python - "$DEMO" <<'PY'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1]); r = json.loads((d / "result.json").read_text())
print(f"\nDone: turns={r.get('num_turns')} est. cost=${r.get('total_cost_usd', 0):.2f}")
b = json.loads((d / "state" / "bookings.json").read_text())
for w, cats in b["weeks"].items():
    for cat, rec in cats.items():
        print(f"  {cat}: {rec['status']} — {(rec['pick'] or {}).get('title', '')}")
print(f"  submissions recorded by the mock site: {sum(1 for _ in (d / 'submissions.jsonl').open()) if (d / 'submissions.jsonl').exists() else 0}")
print(f"  trace: {d / 'logs' / 'runs' / 'demo.md'}")
PY
exit $RC
