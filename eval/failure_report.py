"""Write docs/failure_tests.md from the failure-probe runs (Phase 7).

    python3 eval/failure_report.py

For each x-case run under eval/runs/improved/x*/1/, pulls the pass/fail
result, the escalations, the stop reason, and the trace lines that show the
failure being detected and handled (retry, backup, escalate).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "eval" / "runs" / "improved"
OUT = ROOT / "docs" / "failure_tests.md"

KEYWORDS = {
    "case5_failure_recovery": r"past|stale|september|sold out|full|waitlist|backup|promote",
    "x1_card_redflag": r"card|tier 3|tier-3|blocker|backup|promote",
    "x2_why_attend": r"why|free-text|tier 2|tier-2|unfillable|pending|question",
    "x3_unclear_page": r"unclear|ticket|treated as full|backup|promote",
    "x4_not_open": r"not open|not_open|opens|daily",
    "x5_telegram_down": r"simulated|retr|again|second attempt|failed once",
    "x6_calendar_error": r"simulated|retr|again|second attempt|failed once",
}


def section(run_dir: Path, case: str) -> list[str]:
    result = json.loads((run_dir / "result.json").read_text())
    meta = json.loads((run_dir / "run.json").read_text())
    desc = json.loads((ROOT / "fixtures" / "cases" / case / "case.json").read_text())["description"]
    traces = sorted((run_dir / "logs" / "runs").glob("*.md"))
    trace = traces[0].read_text() if traces else ""
    m = result["measures"]
    out = [f"## {case}", "", desc, "",
           f"**Result: {'PASS' if result['pass'] else 'FAIL'}.** {m.get('num_turns')} turns, {m.get('tool_calls')} tool calls, "
           f"{(m.get('wall_ms') or 0)//1000}s, est. ${m.get('cost_usd')}. Submissions: {m.get('submissions')}. "
           f"Escalations: {m.get('escalations_appropriate')} appropriate, {m.get('escalations_unnecessary')} unnecessary."]
    if result["failed_conditions"]:
        out.append("Failed conditions: " + "; ".join(result["failed_conditions"]))
    out += ["", "Bookings: " + "; ".join(f"{cat}: {b['booked'] or 'none'} ({'ok' if b['ok'] else 'WRONG'})" for cat, b in result["bookings"].items()), ""]
    esc = re.search(r"## Escalations\n\n(.*?)\n\n## Stop reason", trace, re.S)
    out += ["**Escalations (from the trace):**", "", (esc.group(1) if esc else "(none)"), ""]
    stop = re.search(r"## Stop reason\n\n(.*?)(?:\n\n|\Z)", trace, re.S)
    out += ["**Stop reason:** " + (stop.group(1).strip() if stop else "(none)"), ""]
    pat = re.compile(KEYWORDS.get(case, r"backup|retry|escalat"), re.I)
    # Prefer the agent's own narrative (EVALUATE / DECIDE / OBSERVE) over raw ACT lines.
    narrative = [ln for ln in trace.splitlines() if ln.startswith("- ") and "[ACT]" not in ln and pat.search(ln)]
    acts = [ln for ln in trace.splitlines() if ln.startswith("- ") and "[ACT]" in ln and pat.search(ln)]
    seen, lines = set(), []
    for ln in narrative + acts:  # the same sentence can appear in Loop and in Decisions
        key = ln.split("] ", 1)[-1][:120]
        if key not in seen:
            seen.add(key); lines.append(ln)
    out += ["**Trace lines showing detection and handling** (filtered by keyword):", ""]
    out += [ln[:300] for ln in lines[:14]] or ["(no matching lines)"]
    out.append("")
    outbox = run_dir / "state" / "telegram_outbox.jsonl"
    if case == "x5_telegram_down" and outbox.exists():
        rows = [json.loads(l) for l in outbox.open()]
        out += ["**Telegram outbox delivery sequence** (`state/telegram_outbox.jsonl`; the first send fails, the same message is re-sent):", ""]
        out += [f"- {r['kind']}: **{r['delivered']}** — {r['text'][:70]!r}" for r in rows]
        out.append("")
    return out


def main() -> None:
    cases = ["case5_failure_recovery"] + sorted(p.name for p in RUNS.iterdir() if p.name.startswith("x"))
    lines = ["# Failure tests (Phase 7)", "",
             "Each case runs the improved configuration in fixture mode with one realistic failure injected. "
             "The main failure test is `case5_failure_recovery` (top pick full + stale listing). "
             "The x-cases probe the other recovery paths: tier-3 form, tier-2 question, unclear page, registration not open, "
             "Telegram outage, calendar API error. Results are scored by `eval/check.py` from the mock site's records, "
             "the run's state files and the trace.", ""]
    for case in cases:
        run_dir = RUNS / case / "1"
        if (run_dir / "result.json").exists():
            lines += section(run_dir, case)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
