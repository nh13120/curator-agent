"""PostToolUse hook: append every tool call to logs/tool_calls.jsonl.

Claude Code runs this after each tool call (main agent and subagents alike)
and pipes a JSON description on stdin. We write one redacted line per call to
$CURATOR_STATE_DIR/logs/tool_calls.jsonl, and, when a run trace exists, one
"[ACTION]" bullet to it so the trace's action list is complete even if the
model forgets to log a step.

Standard library only, always exits 0: a logging hook must never break a run.
"""

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

SECRET = re.compile(r"(bot\d{6,}:[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{16,}|ya29\.[A-Za-z0-9_-]+)")
SECRET_KEYS = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cvv|card)", re.I)


def redact(value):
    if isinstance(value, dict):
        return {k: ("***" if SECRET_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET.sub("***", value)
    return value


def summarize(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(redact(value), ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    state_dir = Path(os.environ.get("CURATOR_STATE_DIR") or payload.get("cwd") or ".")
    run_id = os.environ.get("CURATOR_RUN_ID", "")
    response = payload.get("tool_response")
    resp_text = summarize(response, 160) if response is not None else ""
    ok = not re.match(r'^\s*(\{"ok":\s*false|### Error|Error:)', resp_text)
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "session_id": payload.get("session_id"),
        "run_id": run_id,
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type") or "main",
        "tool_name": payload.get("tool_name"),
        "input_summary": summarize(payload.get("tool_input", {}), 200),
        "response_summary": resp_text,
        "ok": ok,
    }
    try:
        log = state_dir / "logs" / "tool_calls.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # Feed the run trace (tools/trace.py renders it): one ACT entry per call.
        name = os.environ.get("CURATOR_TRACE_NAME") or run_id
        side = state_dir / "logs" / "runs" / f"{name}.jsonl" if name else None
        if side and side.exists():
            entry = {"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "kind": "action",
                     "text": "", "tool": row["tool_name"], "input": row["input_summary"][:160],
                     "result": resp_text[:160], "ok": ok, "agent_type": row["agent_type"]}
            with side.open("a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
