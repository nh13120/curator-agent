"""Homework deadlines.

    python3 tools/deadlines.py list [--from 2026-10-26 --to 2026-11-01]
    python3 tools/deadlines.py blocked-evenings --from 2026-10-26 --to 2026-11-01

Two sources, merged: calendar entries whose title says "due", "deadline" or
"submission" (always), and an optional Canvas deadline ledger (a JSON file
with `assignments: {id: {title, due_at, submitted}}`, pointed to by
CURATOR_DEADLINES_LEDGER). Curator only reads the ledger; when it is absent
the calendar is the only source. Rule served here: no event after the evening
cutoff on the day BEFORE a day with an unsubmitted deadline.

`submitted: null` means Canvas does not track submissions for that course; we
treat it as unsubmitted (conservative). A ledger older than 36 hours triggers a
warning so a stale file cannot silently disable the rule.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from pathlib import Path

import _common as c

DEFAULT_LEDGER = ""  # none: set CURATOR_DEADLINES_LEDGER in .env to add a Canvas ledger
STALE_AFTER_HOURS = 36


def ledger_path() -> Path | None:
    if c.MODE == "fixture":
        return c.fixture_path("deadlines.json")
    configured = os.environ.get("CURATOR_DEADLINES_LEDGER") or DEFAULT_LEDGER
    return Path(configured).expanduser() if configured else None


def load() -> dict:
    path = ledger_path()
    data = c.load_json(path) if path else None
    if data is None:
        # No ledger configured or file missing: calendar deadlines still apply.
        return {"ok": True, "deadlines": [], "source": str(path) if path else "none (calendar only)",
                "ledger_last_run": None, "warning": None if not path else f"ledger not found: {path}; using calendar deadlines only"}
    rows = []
    for aid, a in (data.get("assignments") or {}).items():
        if not a.get("due_at"):
            continue
        due = c.parse_dt(a["due_at"])
        rows.append({
            "id": aid,
            "title": a.get("title", ""),
            "due_at_utc": a["due_at"],
            "due_local": due.isoformat(),
            "due_date": due.date().isoformat(),
            "submitted": bool(a.get("submitted")),
            "tracked": a.get("submitted") is not None,
        })
    rows.sort(key=lambda r: r["due_local"])
    warning = None
    last_run = data.get("last_run")
    if last_run:
        age_h = (c.now() - c.parse_dt(last_run)).total_seconds() / 3600
        if age_h > STALE_AFTER_HOURS:
            warning = f"ledger last refreshed {age_h:.0f} h ago (> {STALE_AFTER_HOURS} h); deadline data may be stale"
    else:
        warning = "ledger has no last_run stamp"
    return {"ok": True, "deadlines": rows, "source": str(path), "ledger_last_run": last_run, "warning": warning}


def in_range(row: dict, start: str | None, end: str | None) -> bool:
    d = row["due_date"]
    return (not start or d >= start) and (not end or d <= end)


DEADLINE_WORDS = re.compile(r"\b(due|deadline|submission)\b", re.I)
# All-day entries count only when they clearly name coursework: imported academic
# calendars carry administrative "deadline" days (add/drop, cross-registration).
HOMEWORK_WORDS = re.compile(r"\b(hw|homework|assignment|pset|problem set|project|paper|essay|exam|quiz|slides)\b", re.I)


def calendar_deadlines(start: str | None, end: str | None) -> list[dict]:
    """Calendar entries such as 'AI Studio - HW6 due' are deadlines too: courses
    the Canvas ledger does not track still put their dates on the calendar.
    Treated as unsubmitted."""
    if not start or not end:
        return []
    import datetime as _dt

    import gcal

    s = _dt.datetime.combine(_dt.date.fromisoformat(start), _dt.time.min, tzinfo=c.TZ)
    e = _dt.datetime.combine(_dt.date.fromisoformat(end), _dt.time.max, tzinfo=c.TZ) + _dt.timedelta(days=1)
    data = gcal.list_events(s, e)
    rows = []
    for ev in data.get("events", []) if data.get("ok") else []:
        title = ev.get("summary", "")
        if DEADLINE_WORDS.search(title) and (not ev.get("all_day") or HOMEWORK_WORDS.search(title)):
            due = c.parse_dt(ev["start"] if not ev.get("all_day") else ev["start"] + "T23:59:00")
            rows.append({"id": "cal:" + str(ev.get("id")), "title": ev["summary"], "due_at_utc": due.astimezone(dt.timezone.utc).isoformat(),
                         "due_local": due.isoformat(), "due_date": due.date().isoformat(), "submitted": False,
                         "tracked": False, "source": "calendar"})
    return rows


def blocked_evenings(rows: list[dict], start: str | None, end: str | None) -> list[dict]:
    """Days on which evening events are forbidden: the day before each
    unsubmitted deadline. The range filter applies to the blocked day."""
    out = []
    seen_dates = set()
    for r in rows + calendar_deadlines(start, end):
        if r["submitted"]:
            continue
        day_before = (dt.date.fromisoformat(r["due_date"]) - dt.timedelta(days=1)).isoformat()
        if (day_before, r["title"]) in seen_dates:
            continue
        seen_dates.add((day_before, r["title"]))
        if (not start or day_before >= start) and (not end or day_before <= end):
            out.append({"date": day_before, "because": r["title"], "deadline_date": r["due_date"], "deadline_local": r["due_local"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verb", choices=["list", "blocked-evenings"])
    ap.add_argument("--from", dest="start", help="YYYY-MM-DD inclusive")
    ap.add_argument("--to", dest="end", help="YYYY-MM-DD inclusive")
    a = ap.parse_args()
    data = load()
    if not data["ok"]:
        c.out(data, exit_code=1)
    rules = c.load_yaml(c.PROJECT_ROOT / "config" / "rules.yaml", default={}) or {}
    cutoff = rules.get("evening_cutoff", "17:00")
    if a.verb == "list":
        rows = [r for r in data["deadlines"] if in_range(r, a.start, a.end)]
        c.out({**data, "deadlines": rows, "evening_cutoff": cutoff, **c.context_summary()})
    else:
        c.out({"ok": True, "blocked_evenings": blocked_evenings(data["deadlines"], a.start, a.end),
               "evening_cutoff": cutoff, "rule": f"no event starting after {cutoff} on these dates",
               "warning": data.get("warning"), "source": data["source"], **c.context_summary()})


if __name__ == "__main__":
    main()
