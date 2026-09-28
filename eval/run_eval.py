"""Evaluation harness: run fixture cases headlessly and score them.

    python3 eval/run_eval.py run --config baseline|improved --case all|<case> [--runs 3] [--model M] [--force] [--out-root DIR]
    python3 eval/run_eval.py report                 # aggregate result.json files into eval/results.md
    python3 eval/run_eval.py recheck --config X     # re-score existing runs with the current checker

Each run gets its own folder eval/runs/<config>/<case>/<n>/ holding the
mock-site submissions, the agent's state and logs, the raw Claude stream, and
the checker's result.json. A run that already has result.json is skipped
unless --force is given, so an interrupted batch can be resumed.

Both configurations get the same model, the same turn and dollar caps, the
same mock site and the same Python tools. Only the harness differs:

  baseline  one prompt with the rules in plain language, no CLAUDE.md, no
            subagents, no skills, no memory, structured JSON answer.
  improved  the Curator configuration: CLAUDE.md, /plan-week skill, scout and
            verifier subagents, memory files, trace, budget hook.

Run this from a terminal, not from inside a Claude Code session.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _common as c  # noqa: E402  (re-execs under .venv)

RUNS = ROOT / "eval" / "runs"
CASES = ROOT / "fixtures" / "cases"
SITE_PORT = 8765
SITE_URL = f"http://127.0.0.1:{SITE_PORT}"
CLAUDE_TIMEOUT_S = 40 * 60
MAX_TURNS = 150
MAX_BUDGET_USD = 6.0
# One model for both configurations (fairness). Override with --model.
DEFAULT_MODEL = "claude-opus-5"   # claude-opus-5-5 needs Claude Code >= 2.1.280
# Tools neither configuration may use: they could reach outside the run.
SHARED_DISALLOWED = ["WebSearch", "WebFetch", "Workflow", "SendMessage", "ListAgents", "Monitor",
                     "CronCreate", "CronDelete", "RemoteTrigger", "PushNotification", "EnterWorktree"]


# ------------------------------------------------------------- mock site ---

def start_site(case: str, run_dir: Path) -> subprocess.Popen:
    log = (run_dir / "site.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "fixtures" / "site" / "server.py"), "--case", case, "--port", str(SITE_PORT),
         "--out", str(run_dir / "submissions.jsonl"), "--requests-log", str(run_dir / "requests.jsonl")],
        stdout=log, stderr=subprocess.STDOUT)
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{SITE_URL}/health", timeout=1) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("mock site did not start; is port 8765 busy?")


# ------------------------------------------------------- claude command ---

def child_env(run_dir: Path, case: str, run_id: str, today: str, budget: int) -> dict:
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE_CODE_") or k == "CLAUDECODE")}
    env.update({
        "CURATOR_MODE": "fixture",
        "CURATOR_CASE": case,
        "CURATOR_STATE_DIR": str(run_dir),
        "CURATOR_RUN_ID": run_id,
        "CURATOR_TODAY": today,
        "CURATOR_SITE_URL": SITE_URL,
        "CURATOR_TOOL_BUDGET": str(budget),
    })
    return env


def baseline_command(case_meta: dict, mcp_config: Path, model: str | None) -> list[str]:
    tw = dt.date.fromisoformat(case_meta["plan_weeks"][0])
    today = dt.datetime.fromisoformat(case_meta["today"])
    task = (ROOT / "eval" / "baseline" / "task.md").read_text().format(
        weekday=today.strftime("%A"), today=today.date().isoformat(), week_start=tw.isoformat(),
        week_end=(tw + dt.timedelta(days=6)).isoformat(), home_city=case_meta["home_city"],
        source_url=f"{SITE_URL}/api/events.json", profile_path="fixtures/profile.yaml")
    cmd = [
        "claude", "-p", task,
        "--setting-sources", "local",
        "--settings", str(ROOT / "eval" / "baseline" / "settings.json"),
        "--append-system-prompt-file", str(ROOT / "eval" / "baseline" / "prompt.md"),
        "--mcp-config", str(mcp_config), "--strict-mcp-config",
        "--disallowedTools", "Agent", "Skill", "TodoWrite", "Write", "Edit", *SHARED_DISALLOWED,
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-turns", str(MAX_TURNS), "--max-budget-usd", str(MAX_BUDGET_USD),
        "--json-schema", (ROOT / "eval" / "result_schema.json").read_text(),
        "--output-format", "stream-json", "--verbose", "--no-session-persistence",
        "--model", model or DEFAULT_MODEL,
    ]
    return cmd


def improved_command(case_meta: dict, mcp_config: Path, model: str | None) -> list[str]:
    cmd = [
        "claude", "-p", "/plan-week",
        "--setting-sources", "project,local",
        "--settings", str(ROOT / "config" / "modes" / "fixture.json"),
        "--mcp-config", str(mcp_config), "--strict-mcp-config",
        "--disallowedTools", *SHARED_DISALLOWED,
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-turns", str(MAX_TURNS), "--max-budget-usd", str(MAX_BUDGET_USD),
        "--output-format", "stream-json", "--verbose", "--no-session-persistence",
        "--model", model or DEFAULT_MODEL,
    ]
    return cmd


# ------------------------------------------------------------- one run ---

def run_once(config: str, case: str, n: int, model: str | None, force: bool, root: Path = RUNS) -> dict:
    run_dir = root / config / case / str(n)
    if (run_dir / "result.json").exists() and not force:
        print(f"skip {config}/{case}/{n} (done)")
        return json.loads((run_dir / "result.json").read_text())
    if run_dir.exists():
        shutil.rmtree(run_dir)
    for sub in ("state", "memory", "logs/runs", "screenshots"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    case_dir = CASES / case
    case_meta = json.loads((case_dir / "case.json").read_text())
    # Seed memory from the case (the baseline has no memory tools, so the seed
    # is simply never read by it; that asymmetry is the point of the comparison).
    for f in ("history.jsonl", "seen.jsonl"):
        shutil.copy(case_dir / f, run_dir / "memory" / f)
    (run_dir / "state" / "bookings.json").write_text('{"weeks": {}}\n')
    (run_dir / "state" / "pending.json").write_text('{"items": []}\n')

    mcp_config = run_dir / "mcp.json"
    mcp_config.write_text((ROOT / "eval" / "mcp.fixture.template.json").read_text()
                          .replace("__OUTPUT_DIR__", str(run_dir / "screenshots")))

    run_id = f"{config}-{case}-{n}"
    budget = 100000 if config == "baseline" else int(
        (c.load_yaml(ROOT / "config" / "rules.yaml") or {}).get("budgets", {}).get("tool_calls_weekly", 120))
    cmd = (baseline_command if config == "baseline" else improved_command)(case_meta, mcp_config, model)
    env = child_env(run_dir, case, run_id, case_meta["today"], budget)
    if case_meta.get("fault"):
        env["CURATOR_FAULT"] = case_meta["fault"]

    meta = {"config": config, "case": case, "n": n, "run_id": run_id, "model_requested": model,
            "started": dt.datetime.now().isoformat(timespec="seconds"), "command": cmd}
    print(f"run  {config}/{case}/{n} …", flush=True)
    site = start_site(case, run_dir)
    t0 = time.time()
    try:
        with (run_dir / "claude.stream.jsonl").open("w") as out:
            proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.PIPE, text=True,
                                  timeout=CLAUDE_TIMEOUT_S)
        meta["exit_code"] = proc.returncode
        meta["stderr_tail"] = proc.stderr[-4000:]
    except subprocess.TimeoutExpired:
        meta["exit_code"] = -1
        meta["stderr_tail"] = "TIMEOUT"
    finally:
        site.terminate()
        try:
            site.wait(timeout=5)
        except subprocess.TimeoutExpired:
            site.kill()
    meta["wall_ms"] = int((time.time() - t0) * 1000)
    meta["ended"] = dt.datetime.now().isoformat(timespec="seconds")
    meta.update(summarize_stream(run_dir / "claude.stream.jsonl", run_dir / "claude.result.json"))
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n")

    check = subprocess.run([sys.executable, str(ROOT / "eval" / "check.py"), "run", str(run_dir)],
                           capture_output=True, text=True)
    if check.returncode not in (0, 1) or not (run_dir / "result.json").exists():
        print("checker failed:", check.stderr[-2000:])
        result = {"pass": False, "failed_conditions": ["checker crashed"], "measures": {}}
        (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    result = json.loads((run_dir / "result.json").read_text())
    m = result.get("measures", {})
    print(f"     {'PASS' if result.get('pass') else 'FAIL'}  violations={m.get('rule_violations')} "
          f"tool_calls={m.get('tool_calls')} turns={m.get('num_turns')} cost=${m.get('cost_usd')} "
          f"{m.get('wall_ms', 0) // 1000}s  {result.get('failed_conditions')}", flush=True)
    return result


def summarize_stream(stream: Path, result_out: Path) -> dict:
    """Pull the init event (model, tools) and the final result out of the
    stream-json log, and count tool_use blocks (main vs subagent)."""
    info = {"model": None, "tools": [], "tool_calls_main": 0, "tool_calls_subagent": 0, "result": None}
    final = None
    if not stream.exists():
        return info
    with stream.open() as f:
        for line in f:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = msg.get("type")
            if t == "system" and msg.get("subtype") == "init":
                info["model"] = msg.get("model")
                info["tools"] = msg.get("tools", [])
            elif t == "assistant":
                for block in (msg.get("message") or {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if msg.get("parent_tool_use_id"):
                            info["tool_calls_subagent"] += 1
                        else:
                            info["tool_calls_main"] += 1
            elif t == "result":
                final = msg
    if final:
        result_out.write_text(json.dumps(final, indent=2) + "\n")
        info["result"] = {k: final.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms",
                                                    "total_cost_usd", "stop_reason")}
    return info


# --------------------------------------------------------------- report ---

def collect() -> list[dict]:
    rows = []
    for res in sorted(RUNS.glob("*/*/*/result.json")):
        run_dir = res.parent
        meta = json.loads((run_dir / "run.json").read_text()) if (run_dir / "run.json").exists() else {}
        r = json.loads(res.read_text())
        rows.append({"config": run_dir.parts[-3], "case": run_dir.parts[-2], "n": int(run_dir.name),
                     "model": meta.get("model"), **r})
    return rows


def report() -> str:
    rows = collect()
    if not rows:
        return "no runs yet\n"
    cases = sorted({r["case"] for r in rows})
    configs = [cfg for cfg in ("baseline", "improved") if any(r["config"] == cfg for r in rows)]
    cols = ["pass", "rule_violations", "calendar_conflicts", "invalid_events_booked",
            "escalations_appropriate", "escalations_unnecessary", "tool_calls", "num_turns", "wall_s", "cost_usd"]
    lines = ["# Evaluation results", "",
             f"Generated {dt.datetime.now().isoformat(timespec='minutes')}. Each case ran {max(r['n'] for r in rows)} times per configuration in fixture mode "
             "(mock event site, frozen clock 2026-09-26, target week 2026-10-26). Same model, same turn and dollar caps, same tools; only the harness differs.",
             ""]
    models = sorted({str(r.get("model")) for r in rows})
    lines += [f"Models seen: {', '.join(models)}", ""]

    lines += ["## Per run", "", "| config | case | run | " + " | ".join(cols) + " | failed conditions |",
              "|" + "---|" * (len(cols) + 4)]
    for r in sorted(rows, key=lambda r: (r["case"], r["config"], r["n"])):
        m = r.get("measures", {})
        vals = [("PASS" if r.get("pass") else "FAIL")] + [
            str(round(m.get("wall_ms", 0) / 1000)) if col == "wall_s" else str(m.get(col, "")) for col in cols[1:]]
        fails = "; ".join(r.get("failed_conditions", []))[:160]
        lines.append(f"| {r['config']} | {r['case']} | {r['n']} | " + " | ".join(vals) + f" | {fails} |")

    eval_rows = [r for r in rows if r["case"].startswith("case")]
    lines += ["", "## Summary per configuration (the five evaluation cases only; x-probes excluded)", "",
              "| config | pass rate | rule violations (mean) | conflicts (mean) | invalid bookings (mean) | appropriate escalations (mean) | unnecessary escalations (mean) | tool calls (mean, min–max) | seconds (mean) | cost USD (mean, total) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for cfg in configs:
        rs = [r for r in eval_rows if r["config"] == cfg]
        ms = [r.get("measures", {}) for r in rs]

        def mean(key):
            vals = [m.get(key) for m in ms if isinstance(m.get(key), (int, float))]
            return sum(vals) / len(vals) if vals else 0.0

        tcs = [m.get("tool_calls", 0) for m in ms]
        costs = [m.get("cost_usd") or 0 for m in ms]
        lines.append(f"| {cfg} | {sum(1 for r in rs if r.get('pass'))}/{len(rs)} | {mean('rule_violations'):.1f} | "
                     f"{mean('calendar_conflicts'):.1f} | {mean('invalid_events_booked'):.1f} | "
                     f"{mean('escalations_appropriate'):.1f} | {mean('escalations_unnecessary'):.1f} | "
                     f"{mean('tool_calls'):.0f} ({min(tcs, default=0)}–{max(tcs, default=0)}) | "
                     f"{mean('wall_ms') / 1000:.0f} | {mean('cost_usd'):.2f} (${sum(costs):.2f}) |")

    lines += ["", "## Per case pass counts", "", "| case | " + " | ".join(configs) + " |", "|---|" + "---|" * len(configs)]
    for case in cases:
        cells = []
        for cfg in configs:
            rs = [r for r in rows if r["config"] == cfg and r["case"] == case]
            cells.append(f"{sum(1 for r in rs if r.get('pass'))}/{len(rs)}" if rs else "–")
        lines.append(f"| {case} | " + " | ".join(cells) + " |")

    lines += ["", "## Failure notes (generated)", ""]
    for r in sorted(rows, key=lambda r: (r["config"], r["case"], r["n"])):
        if not r.get("pass") or r.get("notes"):
            notes = r.get("notes") or []
            lines.append(f"- **{r['config']} / {r['case']} / run {r['n']}**: "
                         + ("; ".join(r.get("failed_conditions", [])) or "passed")
                         + (" — " + " ".join(notes) if notes else ""))
    # Human-written analysis lives in eval/notes.md so regenerating never loses it.
    notes_md = ROOT / "eval" / "notes.md"
    if notes_md.exists():
        lines += ["", notes_md.read_text().rstrip()]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ cli ---

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("run")
    p.add_argument("--config", choices=["baseline", "improved"], required=True)
    p.add_argument("--case", default="all")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--model", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--out-root", default=None,
                   help="write runs under this folder instead of eval/runs (a side experiment: results.md is left alone)")
    sub.add_parser("report")
    p = sub.add_parser("recheck")
    p.add_argument("--config", choices=["baseline", "improved"], required=True)
    a = ap.parse_args()

    if a.verb == "run":
        cases = sorted(p.name for p in CASES.iterdir() if p.is_dir() and p.name.startswith("case")) \
            if a.case == "all" else [a.case]
        summary = []
        for case in cases:
            for n in range(1, a.runs + 1):
                r = run_once(a.config, case, n, a.model, a.force, Path(a.out_root).resolve() if a.out_root else RUNS)
                summary.append((case, n, r.get("pass")))
        passed = sum(1 for _, _, ok in summary if ok)
        print(f"\n{a.config}: {passed}/{len(summary)} passed")
        if not a.out_root:
            (ROOT / "eval" / "results.md").write_text(report())
            print("wrote eval/results.md")
    elif a.verb == "recheck":
        for run_dir in sorted((RUNS / a.config).glob("*/*")):
            if (run_dir / "run.json").exists():
                subprocess.run([sys.executable, str(ROOT / "eval" / "check.py"), "run", str(run_dir)], check=False,
                               capture_output=True)
                r = json.loads((run_dir / "result.json").read_text())
                print(f"{run_dir.relative_to(RUNS)}: {'PASS' if r.get('pass') else 'FAIL'} {r.get('failed_conditions')}")
        (ROOT / "eval" / "results.md").write_text(report())
        print("wrote eval/results.md")
    else:
        text = report()
        (ROOT / "eval" / "results.md").write_text(text)
        print(text)


if __name__ == "__main__":
    main()
