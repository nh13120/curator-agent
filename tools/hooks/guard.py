"""PreToolUse hook: code-enforced guardrails.

Claude Code runs this before every tool call and pipes a JSON description on
stdin. Printing a JSON decision with permissionDecision "deny" blocks the call
and shows the reason to the model. Silence (exit 0, no output) lets the normal
permission flow decide. The rules here hold no matter what the prompt says:

  1. Tier 3 fields. Typing or filling anything that looks like a password,
     card number, CVV, expiry, SSN, passport or driver's licence is denied in
     every mode. The agent must stop and hand the form to Nicolas.
  2. Fixture mode pins the browser to the mock site (belt; the Playwright
     server's --allowed-origins is the braces).
  3. Scout and verifier subagents may only run `python3 tools/fetch.py`.
  4. Tool-call budget. When CURATOR_TOOL_BUDGET is set and the run's count in
     logs/tool_calls.jsonl has reached it, further calls are denied except the
     reporting tools (trace, telegram), so the agent can record the stop.

Standard library only. Any internal error exits 0 silently: a broken guard
must not take the whole run down, and the browser-level and tool-level guards
still apply.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

SENSITIVE = re.compile(
    r"(password|passcode|pass\s?word|card\s?(number|no\.?|#)|credit\s?card|debit|cvv|cvc|csc|security\s?code|"
    r"expir(y|ation)|exp\.?\s?date|ssn|social\s?security|passport|driver'?s?\s?licen[cs]e|national\s?id|"
    r"tax\s?id|routing\s?number|account\s?number|iban)", re.I)
READONLY_AGENTS = {"scout", "verifier"}
BUDGET_EXEMPT = ("python3 tools/trace.py", "python3 tools/telegram.py", "python3 tools/pending.py")


FETCH_FLAGS = {"--listing": 0, "--event": 0, "--window": 1, "--max-chars": 1}


def fetch_command_ok(cmd: str) -> bool:
    """True only for `python3 tools/fetch.py <url> [flags]` with no shell
    operators, substitutions or redirections. A quoted URL may contain `&`
    (query strings do); an unquoted `&`, `;`, `|`, `<`, `>` is an operator."""
    if any(x in cmd for x in ("`", "$(", "${", "\n", "\r")):
        return False
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return False
    if len(toks) < 3 or toks[0] != "python3" or toks[1] != "tools/fetch.py":
        return False
    if any(t and set(t) <= set(";&|<>()") for t in toks):
        return False
    url, rest = toks[2], toks[3:]
    if not re.match(r"^https?://\S+$", url):
        return False
    i = 0
    while i < len(rest):
        n = FETCH_FLAGS.get(rest[i])
        if n is None:
            return False
        i += 1 + n
    return i == len(rest)


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def field_descriptions(tool_input: dict) -> str:
    """Text that describes WHICH fields are being filled (not the values)."""
    parts = [str(tool_input.get("element", ""))]
    for f in tool_input.get("fields", []) or []:
        if isinstance(f, dict):
            parts.append(str(f.get("name", "")) + " " + str(f.get("type", "")))
    return " ".join(parts)


def count_calls(state_dir: Path, run_id: str) -> int:
    log = state_dir / "logs" / "tool_calls.jsonl"
    if not log.exists():
        return 0
    n = 0
    with log.open() as f:
        for line in f:
            if not run_id or f'"run_id": "{run_id}"' in line:
                n += 1
    return n


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input") or {}
    agent_type = payload.get("agent_type") or "main"
    mode = os.environ.get("CURATOR_MODE", "dry")
    site = os.environ.get("CURATOR_SITE_URL", "http://127.0.0.1:8765").rstrip("/")
    short = tool.split("__")[-1]  # mcp__playwright__browser_type -> browser_type

    # 1. Tier 3 fields, every mode.
    if short in ("browser_type", "browser_fill_form", "browser_press_key", "browser_select_option"):
        desc = field_descriptions(tool_input)
        if SENSITIVE.search(desc):
            deny("Tier 3 blocker: this looks like a password, payment or government-ID field. Never fill it. "
                 "Take a screenshot, record the blocker in the trace, and report it to Nicolas instead.")

    # 2. Fixture mode: browser stays on the mock site.
    if short == "browser_navigate" and mode == "fixture":
        url = str(tool_input.get("url", ""))
        if not url.startswith(site + "/") and url != site:
            deny(f"Fixture mode: the browser may only visit {site}. Nothing real is contacted during tests.")

    # 3. Read-only subagents: shell limited to the fetch tool.
    if agent_type in READONLY_AGENTS and tool == "Bash":
        cmd = str(tool_input.get("command", "")).strip()
        if not fetch_command_ok(cmd):
            deny(f"The {agent_type} subagent is read-only: the only shell command allowed is "
                 '`python3 tools/fetch.py "<url>" [--listing --window A..B | --event]`, with the URL in double quotes.')

    # 4. Tool-call budget for this run.
    budget = os.environ.get("CURATOR_TOOL_BUDGET")
    if budget and budget.isdigit():
        state_dir = Path(os.environ.get("CURATOR_STATE_DIR") or payload.get("cwd") or ".")
        run_id = os.environ.get("CURATOR_RUN_ID", "")
        cmd = str(tool_input.get("command", "")) if tool == "Bash" else ""
        exempt = tool == "Bash" and cmd.strip().startswith(BUDGET_EXEMPT)
        if not exempt and count_calls(state_dir, run_id) >= int(budget):
            deny(f"Run budget reached ({budget} tool calls). Stopping condition hit: write the stop reason "
                 "'budget_hit' to the trace with `python3 tools/trace.py stop`, send the summary, and finish. "
                 "Do not start new work.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
