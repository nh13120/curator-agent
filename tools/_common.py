"""Shared plumbing for every Curator tool script.

Every tool in tools/ imports this module. It answers four questions once so no
tool has to answer them itself:

  1. Which MODE are we in?   live | dry | fixture   (env CURATOR_MODE, default dry)
  2. Which fixture CASE?     fixtures/cases/<CURATOR_CASE>/   (fixture mode only)
  3. Where is state kept?    CURATOR_STATE_DIR (default: project root)
  4. What time is it?        CURATOR_TODAY freezes the clock in fixture mode

The important safety rule lives here too: `require_write()` raises unless the
mode is `live`, so no tool can submit a form, write to the real calendar, or
send a real Telegram message in dry or fixture mode, whatever the prompt says.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------
# Re-exec under the project's virtualenv.
#
# Tools are invoked as `python3 tools/<name>.py ...` from skills, hooks and
# launchd. The system python3 does not have pyyaml/jsonschema installed, the
# .venv does. If we are not already running inside the .venv, restart this
# same script with the .venv interpreter. This keeps one CLI convention
# everywhere without asking callers to remember the venv path.
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_DIR = PROJECT_ROOT / ".venv"
_VENV_PYTHON = _VENV_DIR / "bin" / "python"
# sys.prefix is the venv folder when running inside it. (We cannot compare
# interpreter paths: the venv's python is a symlink to the system binary.)
if _VENV_PYTHON.exists() and Path(sys.prefix).resolve() != _VENV_DIR.resolve():
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

TZ = ZoneInfo("America/New_York")

# Secrets and local settings come from .env (gitignored). Values already in the
# environment win, so a launcher or the eval harness can override them.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # only outside the venv, which the re-exec above prevents
    pass

MODE = os.environ.get("CURATOR_MODE", "dry").strip().lower()
if MODE not in ("live", "dry", "fixture"):
    raise SystemExit(f"CURATOR_MODE must be live, dry or fixture (got {MODE!r})")

CASE = os.environ.get("CURATOR_CASE") or None
# A selftest never touches real state: without an explicit CURATOR_STATE_DIR
# it gets a throwaway folder (found 2026-09-27: pending/trace selftests had
# written a test item and a trace into the live state).
_SELFTEST = len(sys.argv) > 1 and sys.argv[1] == "selftest"
if _SELFTEST and not os.environ.get("CURATOR_STATE_DIR"):
    import tempfile

    os.environ["CURATOR_STATE_DIR"] = tempfile.mkdtemp(prefix="curator-selftest-")
STATE_DIR = Path(os.environ.get("CURATOR_STATE_DIR") or PROJECT_ROOT).resolve()
SITE_URL = os.environ.get("CURATOR_SITE_URL", "http://127.0.0.1:8765").rstrip("/")
# CURATOR_FAULT lets failure tests make one tool fail on purpose, e.g. "telegram".
FAULT = os.environ.get("CURATOR_FAULT", "").strip().lower()


def run_id() -> str:
    """Stable id for this run. The launcher sets CURATOR_RUN_ID; otherwise we
    make one from the clock so log lines from one run can be grouped."""
    rid = os.environ.get("CURATOR_RUN_ID")
    if not rid:
        rid = now().strftime("%Y%m%d-%H%M%S") + "-adhoc"
        os.environ["CURATOR_RUN_ID"] = rid
    return rid


# ----------------------------------------------------------------- clock ---

def now() -> dt.datetime:
    """Current time in America/New_York. In fixture mode the clock is frozen
    by CURATOR_TODAY (or the case's case.json), so runs are repeatable."""
    frozen = os.environ.get("CURATOR_TODAY")
    if not frozen and MODE == "fixture":
        case = load_json(fixture_path("case.json"), default={})
        frozen = case.get("today")
    if frozen:
        t = dt.datetime.fromisoformat(frozen)
        return t.astimezone(TZ) if t.tzinfo else t.replace(tzinfo=TZ)
    return dt.datetime.now(TZ)


def parse_dt(value: str) -> dt.datetime:
    """Parse an ISO 8601 string. Naive strings are taken as New York time;
    'Z' suffix (Canvas style) is UTC."""
    t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t.astimezone(TZ) if t.tzinfo else t.replace(tzinfo=TZ)


def week_start(day: dt.date) -> dt.date:
    """Monday of the week containing `day`. Weeks run Monday to Sunday."""
    return day - dt.timedelta(days=day.weekday())


# ----------------------------------------------------------------- paths ---

def fixture_dir() -> Path:
    if not CASE:
        raise SystemExit("CURATOR_CASE is required in fixture mode")
    d = PROJECT_ROOT / "fixtures" / "cases" / CASE
    if not d.is_dir():
        raise SystemExit(f"fixture case not found: {d}")
    return d


def fixture_path(name: str) -> Path:
    return fixture_dir() / name


def state_path(rel: str) -> Path:
    """Path under the state dir; parent folders are created on demand."""
    p = STATE_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def resolve(path: str | Path) -> Path:
    """Tool file arguments: absolute paths stay as they are; relative paths are
    taken under the state dir, so `state/candidates/ai.json` lands in the run's
    own folder during an evaluation and in the project during a live run."""
    p = Path(path)
    return p if p.is_absolute() else (STATE_DIR / p)


def profile_path() -> Path:
    """The form-filling profile. Real one is gitignored; fixtures use a fake."""
    if MODE == "fixture":
        return PROJECT_ROOT / "fixtures" / "profile.yaml"
    return PROJECT_ROOT / "config" / "profile.yaml"


# ------------------------------------------------------------- file i/o ---

def load_json(path: Path | str, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with p.open() as f:
        return json.load(f)


def write_json_atomic(path: Path | str, obj) -> None:
    """Write JSON via a temp file + rename so a crash never leaves half a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def append_jsonl(path: Path | str, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path | str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_yaml(path: Path | str, default=None):
    import yaml  # imported lazily: only present inside the .venv

    p = Path(path)
    if not p.exists():
        return default
    with p.open() as f:
        return yaml.safe_load(f) or default


# --------------------------------------------------------------- output ---

def out(obj, exit_code: int = 0) -> None:
    """Every tool prints exactly one JSON object on stdout."""
    print(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    sys.stdout.flush()
    if exit_code:
        raise SystemExit(exit_code)


def fail(message: str, **extra) -> None:
    out({"ok": False, "error": message, **extra}, exit_code=1)


# ------------------------------------------------------------ guardrails ---

class ModeBlocked(Exception):
    """Raised when a side effect is attempted outside live mode."""


def log_write_attempt(kind: str, payload=None, *, blocked: bool, simulated: bool = False) -> None:
    """Every side effect, real, simulated or blocked, is recorded in
    logs/writes.jsonl. In dry mode the file shows what *would* have happened;
    in fixture mode it shows what the fake systems received; in live mode it
    is the audit trail."""
    append_jsonl(state_path("logs/writes.jsonl"), {
        "ts": now().isoformat(),
        "run_id": run_id(),
        "mode": MODE,
        "kind": kind,
        "blocked": blocked,
        "simulated": simulated,
        "payload": redact(payload),
    })


def require_write(action: str, payload=None) -> str:
    """Call this before any side effect.

    live    -> returns "live": go ahead against the real system.
    fixture -> returns "simulated": write to the fake store under STATE_DIR.
    dry     -> raises ModeBlocked; nothing may be written anywhere.
    """
    if MODE == "dry":
        log_write_attempt(action, payload, blocked=True)
        raise ModeBlocked(action)
    simulated = MODE == "fixture"
    log_write_attempt(action, payload, blocked=False, simulated=simulated)
    return "simulated" if simulated else "live"


def blocked_response(action: str, **extra) -> dict:
    """Uniform JSON a tool returns when require_write() refused."""
    return {"ok": False, "blocked_by": "mode", "mode": MODE, "action": action, **extra}


_SECRET_KEY = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cvv|card)", re.I)
_SECRET_INLINE = re.compile(r"(bot\d{6,}:[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{16,}|ya29\.[A-Za-z0-9_-]+)")


def redact(value):
    """Mask anything that looks like a secret so it never lands in a log."""
    if isinstance(value, dict):
        return {k: ("***" if _SECRET_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _SECRET_INLINE.sub("***", value)
    return value


# -------------------------------------------------------------- identity ---

def norm(text: str) -> str:
    """Normalize text for matching: lowercase, no accents, no punctuation,
    single spaces, leading 'the ' dropped. Used for ids and dedupe keys."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def event_id(title: str, date: str, venue: str) -> str:
    """Stable event id shared by the tools, the mock site and the checker.
    `date` is YYYY-MM-DD of the event (opening day for exhibitions)."""
    key = f"{norm(title)}|{date[:10]}|{norm(venue)}"
    return "ev_" + hashlib.sha1(key.encode()).hexdigest()[:12]


def talk_key(title: str, speakers: list[str]) -> str:
    """Key for 'same speaker, same talk' detection across venues and dates."""
    names = sorted(norm(s) for s in speakers if s)
    return "|".join(names) + "||" + norm(title)


def exhibition_key(title: str, venue: str) -> str:
    """Key for 'same exhibition at the same venue' regardless of visit date."""
    return norm(title) + "||" + norm(venue)


def context_summary() -> dict:
    """Small dict every tool can include so logs show the mode they ran in."""
    return {"mode": MODE, "case": CASE, "state_dir": str(STATE_DIR), "run_id": run_id()}
