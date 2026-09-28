"""Run trace: the observable agent loop.

    python3 tools/trace.py start --goal "..." [--kind weekly|daily|adhoc]
    python3 tools/trace.py append --section plan|action|observe|evaluate|decision|escalation|note --text "..."
    python3 tools/trace.py stop --reason all_slots_resolved|candidates_exhausted|budget_hit|tier3_blocker|nothing_due|error --text "..."
    python3 tools/trace.py render [--run-id ID]
    python3 tools/trace.py selftest

Every run writes logs/runs/<run_id>.md. Entries are kept in a JSONL sidecar
(logs/runs/<run_id>.jsonl); the PostToolUse hook appends one entry per tool
call there too, so the "Actions" are complete even if the model forgets to
narrate them. Each trace.py call re-renders the Markdown with the sections the
brief asks for: Goal, Plan, Loop (goal → decide → act → observe → evaluate),
Decisions, Escalations, Stop reason.
"""

from __future__ import annotations

import argparse
import json
import os

import _common as c

SECTIONS = ("plan", "action", "observe", "evaluate", "decision", "escalation", "note")
STOP_REASONS = ("all_slots_resolved", "candidates_exhausted", "budget_hit", "tier3_blocker", "nothing_due", "error")
TAG = {"plan": "PLAN", "action": "ACT", "observe": "OBSERVE", "evaluate": "EVALUATE", "decision": "DECIDE",
       "escalation": "ESCALATE", "note": "NOTE", "goal": "GOAL", "stop": "STOP"}


def paths(run_id: str | None = None):
    rid = run_id or c.run_id()
    # CURATOR_TRACE_NAME keeps one file name across runs (the demo opens it in
    # VS Code before the run starts); the run id stays unique per run.
    name = (None if run_id else os.environ.get("CURATOR_TRACE_NAME")) or rid
    return c.state_path(f"logs/runs/{name}.md"), c.state_path(f"logs/runs/{name}.jsonl"), rid


def add(kind: str, text: str, **extra) -> dict:
    md, side, rid = paths()
    entry = {"ts": c.now().isoformat(timespec="seconds"), "kind": kind, "text": text, **extra}
    c.append_jsonl(side, entry)
    render()
    return entry


def render(run_id: str | None = None) -> str:
    md, side, rid = paths(run_id)
    entries = c.read_jsonl(side)
    goal = next((e for e in entries if e["kind"] == "goal"), {})
    stop = next((e for e in entries if e["kind"] == "stop"), None)
    lines = [f"# Run {rid}", "",
             f"Mode `{c.MODE}`" + (f", fixture case `{c.CASE}`" if c.CASE else "") + f", kind `{goal.get('run_kind', 'adhoc')}`, started {goal.get('ts', '?')}.", "",
             "## Goal", "", goal.get("text", "(no goal recorded)"), "",
             "## Plan", ""]
    plans = [e for e in entries if e["kind"] == "plan"]
    lines += [f"- {e['text']}" for e in plans] or ["(no plan recorded)"]
    lines += ["", "## Loop", "", "Chronological: decide → act → observe → evaluate → continue or stop. `ACT` lines with a tool name come from the tool-call hook.", ""]
    n_actions = 0
    for e in entries:
        if e["kind"] in ("goal", "plan", "stop"):
            continue
        t = e["ts"][11:19]
        who = f" ({e['agent_type']})" if e.get("agent_type") and e["agent_type"] != "main" else ""
        if e["kind"] == "action" and e.get("tool"):
            n_actions += 1
            status = "ok" if e.get("ok", True) else "ERROR"
            lines.append(f"- {t} [ACT]{who} `{e['tool']}` {e.get('input', '')[:140]} → {status}: {e.get('result', '')[:140]}")
        else:
            lines.append(f"- {t} [{TAG.get(e['kind'], e['kind'].upper())}] {e['text']}")
    if not any(e["kind"] not in ("goal", "plan", "stop") for e in entries):
        lines.append("(nothing yet)")
    lines += ["", "## Decisions and reasons", ""]
    lines += [f"- {e['text']}" for e in entries if e["kind"] == "decision"] or ["(none)"]
    lines += ["", "## Escalations", ""]
    lines += [f"- {e['text']}" for e in entries if e["kind"] == "escalation"] or ["(none)"]
    lines += ["", "## Stop reason", ""]
    if stop:
        lines.append(f"**{stop['reason']}** — {stop['text']}")
        lines.append(f"\nTool calls recorded: {n_actions}. Ended {stop['ts']}.")
    else:
        lines.append("(run still in progress)")
    md.write_text("\n".join(lines) + "\n")
    return str(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("start"); p.add_argument("--goal", required=True); p.add_argument("--kind", default="adhoc", choices=["weekly", "daily", "adhoc"])
    p = sub.add_parser("append"); p.add_argument("--section", required=True, choices=SECTIONS); p.add_argument("--text", required=True)
    p = sub.add_parser("stop"); p.add_argument("--reason", required=True, choices=STOP_REASONS); p.add_argument("--text", required=True)
    p = sub.add_parser("render"); p.add_argument("--run-id")
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "start":
        e = add("goal", a.goal, run_kind=a.kind)
        c.out({"ok": True, "run_id": c.run_id(), "trace": str(paths()[0]), "entry": e, **c.context_summary()})
    elif a.verb == "append":
        e = add(a.section, a.text)
        c.out({"ok": True, "entry": e})
    elif a.verb == "stop":
        e = add("stop", a.text, reason=a.reason)
        c.out({"ok": True, "entry": e, "trace": str(paths()[0])})
    elif a.verb == "render":
        c.out({"ok": True, "trace": render(a.run_id)})
    else:
        add("goal", "selftest goal", run_kind="adhoc"); add("plan", "step one"); add("decision", "chose A because B")
        add("action", "", tool="Bash", input="python3 tools/clock.py context", result='{"ok": true}', ok=True)
        add("stop", "done", reason="all_slots_resolved")
        text = paths()[0].read_text()
        assert all(h in text for h in ("## Goal", "## Plan", "## Loop", "## Decisions", "## Escalations", "## Stop reason"))
        assert "[DECIDE] chose A" in text and "`Bash`" in text and "**all_slots_resolved**" in text
        c.out({"ok": True, "checks": 2, "trace": str(paths()[0])})


if __name__ == "__main__":
    main()
