"""Bookings ledger: one record per week and category.

    python3 tools/bookings.py get --week 2026-10-26 [--category ai]
    python3 tools/bookings.py set --week 2026-10-26 --category ai --status booked --pick-json <file|->
    python3 tools/bookings.py set --week 2026-10-26 --category ai --status skipped --skip-reason "..."
    python3 tools/bookings.py set ... --registration-state confirmed --confirmation "#12" --screenshot <path>
    python3 tools/bookings.py set ... --calendar-event-id <id> | --backup-json <file> | --ambiguity "..."
    python3 tools/bookings.py mark --week W --category C --field rating_prompt_sent_at --value now
    python3 tools/bookings.py plan --week W --category C --ranked state/candidates/C.ranked.json   # store pick + backup
    python3 tools/bookings.py book --week W --category C --registration-state confirmed --confirmation "#12" --screenshot <path>
    python3 tools/bookings.py skip --week W --category C --reason "..."
    python3 tools/bookings.py promote-backup --week W --category C --reason full|unclear_page|tier3_form
    python3 tools/bookings.py cancel --week W --category C --reason "..."
    python3 tools/bookings.py upcoming
    python3 tools/bookings.py due --kind registration|rating|reminder
    python3 tools/bookings.py selftest

File: state/bookings.json
  {"weeks": {"2026-10-26": {"ai": {status, pick, backup, registration, calendar_event_id,
                                    skip_reason, ambiguities, updated_at}}}}

status: open | booked | skipped | pending | cancelled
registration.state: none | submitted | confirmed | not_open | failed | cancelled
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import _common as c

FILE = "state/bookings.json"
STATUSES = ("open", "booked", "skipped", "pending", "cancelled")
REG_STATES = ("none", "submitted", "confirmed", "not_open", "failed", "cancelled")


def load() -> dict:
    return c.load_json(c.state_path(FILE), default={"weeks": {}})


def save(data: dict) -> None:
    c.write_json_atomic(c.state_path(FILE), data)


def blank() -> dict:
    return {"status": "open", "pick": None, "backup": None,
            "registration": {"state": "none", "attempts": 0, "submitted_at": None, "confirmation": None, "screenshot": None},
            "calendar_event_id": None, "skip_reason": None, "ambiguities": [], "updated_at": None}


def get(week: str, category: str | None) -> dict:
    wk = load()["weeks"].get(week, {})
    return {"ok": True, "week": week, "bookings": {category: wk.get(category, blank())} if category else wk}


def read_json_arg(arg: str):
    return json.load(sys.stdin) if arg == "-" else c.load_json(c.resolve(arg))


def set_(week: str, category: str, **changes) -> dict:
    data = load()
    rec = data["weeks"].setdefault(week, {}).setdefault(category, blank())
    if changes.get("status"):
        rec["status"] = changes["status"]
    if changes.get("pick") is not None:
        pick = changes["pick"]
        pick.setdefault("event_id", c.event_id(pick["title"], pick["start"], pick.get("venue_name", "")))
        rec["pick"] = pick
    if "backup" in changes and (changes["backup"] is not None or changes.get("clear_backup")):
        rec["backup"] = changes["backup"]
    if changes.get("registration_state"):
        rec["registration"]["state"] = changes["registration_state"]
        if changes["registration_state"] == "submitted":
            rec["registration"]["attempts"] += 1
            rec["registration"]["submitted_at"] = c.now().isoformat()
    for k in ("confirmation", "screenshot"):
        if changes.get(k):
            rec["registration"][k] = changes[k]
    if changes.get("calendar_event_id") is not None:
        rec["calendar_event_id"] = changes["calendar_event_id"] or None
    if changes.get("skip_reason"):
        rec["skip_reason"] = changes["skip_reason"]
    if changes.get("ambiguity"):
        rec["ambiguities"].append(changes["ambiguity"])
    rec["updated_at"] = c.now().isoformat()
    save(data)
    return {"ok": True, "week": week, "category": category, "record": rec}


def mark(week: str, category: str, field: str, value: str) -> dict:
    data = load()
    rec = data["weeks"].get(week, {}).get(category)
    if not rec:
        return {"ok": False, "error": f"no record for {week}/{category}"}
    rec[field] = c.now().isoformat() if value == "now" else value
    rec["updated_at"] = c.now().isoformat()
    save(data)
    return {"ok": True, "record": rec}


def all_records() -> list[tuple[str, str, dict]]:
    out = []
    for week, cats in load()["weeks"].items():
        for cat, rec in cats.items():
            out.append((week, cat, rec))
    return sorted(out)


def upcoming() -> dict:
    now = c.now()
    rows = []
    for week, cat, rec in all_records():
        if rec["status"] == "booked" and rec.get("pick") and c.parse_dt(rec["pick"]["start"]) >= now:
            rows.append({"week": week, "category": cat, "title": rec["pick"]["title"], "start": rec["pick"]["start"],
                         "venue": rec["pick"].get("venue_name"), "registration": rec["registration"]["state"],
                         "calendar_event_id": rec["calendar_event_id"]})
    return {"ok": True, "upcoming": sorted(rows, key=lambda r: r["start"])}


def due(kind: str) -> dict:
    """What the daily check must act on.
      registration: booked picks whose registration is not open yet (re-check the page)
      rating:       booked picks that ended and have not been prompted
      reminder:     prompted more than 3 days ago with no rating and no reminder yet
    """
    now = c.now()
    rules = c.load_yaml(c.PROJECT_ROOT / "config" / "rules.yaml", default={}) or {}
    remind_days = (rules.get("ratings") or {}).get("reminder_after_days", 3)
    unconfirmed_days = (rules.get("ratings") or {}).get("unconfirmed_after_days", 6)
    rows = []
    for week, cat, rec in all_records():
        pick = rec.get("pick")
        if not pick or rec["status"] not in ("booked", "open", "pending"):
            continue
        end = c.parse_dt(pick.get("end") or pick["start"])
        row = {"week": week, "category": cat, "event_id": pick.get("event_id"), "title": pick["title"], "start": pick["start"], "end": pick.get("end")}
        if kind == "registration" and rec["registration"]["state"] == "not_open":
            rows.append({**row, "opens_at": pick.get("opens_at")})
        elif kind == "rating" and rec["status"] == "booked" and end < now and not rec.get("rating_prompt_sent_at") and not rec.get("rated_at"):
            rows.append(row)
        elif kind == "reminder" and rec.get("rating_prompt_sent_at") and not rec.get("rated_at"):
            sent = c.parse_dt(rec["rating_prompt_sent_at"])
            age = (now - sent).days
            if not rec.get("rating_reminder_sent_at") and age >= remind_days:
                rows.append({**row, "action": "send_reminder", "days_since_prompt": age})
            elif rec.get("rating_reminder_sent_at") and age >= unconfirmed_days:
                rows.append({**row, "action": "mark_unconfirmed", "days_since_prompt": age})
    return {"ok": True, "kind": kind, "due": rows}


def pick_summary(pick: dict | None) -> dict | None:
    if not pick:
        return None
    keys = ("event_id", "title", "start", "end", "venue_name", "venue_address", "city", "category", "format",
            "price_label", "registration_state", "registration_url", "event_url", "speaker_tier", "venue_tier",
            "format_tier", "travel_min", "taste_fit", "flags", "ineligible_reasons")
    return {k: pick.get(k) for k in keys if k in pick}


def plan(week: str, category: str, ranked_file: str) -> dict:
    """Store the ranker's pick and backup for this slot (status stays open until booked)."""
    ranked = read_json_arg(ranked_file)
    pick, backup = ranked.get("pick"), ranked.get("backup")
    if not pick:
        return {"ok": True, "week": week, "category": category, "pick": None,
                "note": ranked.get("none_eligible_reason") or "no eligible candidate"}
    res = set_(week, category, pick=pick, backup=backup, clear_backup=True)  # a new plan replaces any stale backup
    return {"ok": True, "week": week, "category": category, "pick": pick_summary(pick), "backup": pick_summary(backup),
            "why": ranked.get("why"), "pick_needs_ask": ranked.get("pick_needs_ask"), "pick_flags": ranked.get("pick_flags", []),
            "status": res["record"]["status"]}


def book(week: str, category: str, registration_state: str, confirmation: str | None, screenshot: str | None) -> dict:
    """Mark the stored pick as booked and record it in memory/history.jsonl."""
    import memory

    rec = load()["weeks"].get(week, {}).get(category)
    if not rec or not rec.get("pick"):
        return {"ok": False, "error": f"no pick stored for {week}/{category}; run `plan` first"}
    res = set_(week, category, status="booked", registration_state=registration_state, confirmation=confirmation, screenshot=screenshot)
    hist = memory.record(rec["pick"], "booked", week)
    return {"ok": True, "record": res["record"], "history": {"event_id": hist["event_id"], "status": hist["status"]},
            "pick": pick_summary(rec["pick"])}


def skip(week: str, category: str, reason: str) -> dict:
    res = set_(week, category, status="skipped", skip_reason=reason)
    return {"ok": True, "record": res["record"]}


def cancel(week: str, category: str, reason: str) -> dict:
    import memory

    rec = load()["weeks"].get(week, {}).get(category)
    if not rec or not rec.get("pick"):
        return {"ok": False, "error": f"nothing booked for {week}/{category}"}
    res = set_(week, category, status="cancelled", registration_state="cancelled", ambiguity=None)
    res["record"]["cancel_reason"] = reason
    save_rec = load(); save_rec["weeks"][week][category]["cancel_reason"] = reason; save(save_rec)
    memory.set_status(rec["pick"].get("event_id"), "cancelled", note=reason)
    return {"ok": True, "record": res["record"], "calendar_event_id": rec.get("calendar_event_id")}


def promote_backup(week: str, category: str, reason: str) -> dict:
    """The pick fell through (full, unclear page, tier-3 form): the backup becomes the pick."""
    import memory

    rec = load()["weeks"].get(week, {}).get(category)
    if not rec or not rec.get("pick"):
        return {"ok": False, "error": f"no pick stored for {week}/{category}"}
    memory.seen(rec["pick"], reason, permanent=None)
    if not rec.get("backup"):
        set_(week, category, status="open", ambiguity=f"pick dropped ({reason}) and no backup")
        data = load(); data["weeks"][week][category]["pick"] = None; save(data)
        return {"ok": True, "promoted": None, "note": f"pick dropped ({reason}); no backup available: category stays open"}
    data = load(); slot = data["weeks"][week][category]
    slot["pick"], slot["backup"], slot["status"] = slot["backup"], None, "open"
    slot["registration"] = blank()["registration"]; slot["updated_at"] = c.now().isoformat(); save(data)
    return {"ok": True, "promoted": pick_summary(slot["pick"]), "reason": reason}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("get"); p.add_argument("--week", required=True); p.add_argument("--category")
    p = sub.add_parser("set"); p.add_argument("--week", required=True); p.add_argument("--category", required=True)
    p.add_argument("--status", choices=STATUSES); p.add_argument("--pick-json"); p.add_argument("--backup-json")
    p.add_argument("--registration-state", choices=REG_STATES); p.add_argument("--confirmation"); p.add_argument("--screenshot")
    p.add_argument("--calendar-event-id"); p.add_argument("--skip-reason"); p.add_argument("--ambiguity")
    p.add_argument("--clear-backup", action="store_true", help="drop the stored backup")
    p = sub.add_parser("mark"); p.add_argument("--week", required=True); p.add_argument("--category", required=True)
    p.add_argument("--field", required=True); p.add_argument("--value", required=True)
    p = sub.add_parser("plan"); p.add_argument("--week", required=True); p.add_argument("--category", required=True); p.add_argument("--ranked", required=True)
    p = sub.add_parser("book"); p.add_argument("--week", required=True); p.add_argument("--category", required=True)
    p.add_argument("--registration-state", choices=REG_STATES, default="confirmed"); p.add_argument("--confirmation"); p.add_argument("--screenshot")
    p = sub.add_parser("skip"); p.add_argument("--week", required=True); p.add_argument("--category", required=True); p.add_argument("--reason", required=True)
    p = sub.add_parser("cancel"); p.add_argument("--week", required=True); p.add_argument("--category", required=True); p.add_argument("--reason", required=True)
    p = sub.add_parser("promote-backup"); p.add_argument("--week", required=True); p.add_argument("--category", required=True); p.add_argument("--reason", required=True)
    sub.add_parser("upcoming")
    p = sub.add_parser("due"); p.add_argument("--kind", choices=["registration", "rating", "reminder"], required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "get":
        res = get(a.week, a.category)
    elif a.verb == "set":
        res = set_(a.week, a.category, status=a.status,
                   pick=read_json_arg(a.pick_json) if a.pick_json else None,
                   backup=read_json_arg(a.backup_json) if a.backup_json else None,
                   registration_state=a.registration_state, confirmation=a.confirmation, screenshot=a.screenshot,
                   calendar_event_id=a.calendar_event_id, skip_reason=a.skip_reason, ambiguity=a.ambiguity,
                   clear_backup=a.clear_backup)
    elif a.verb == "mark":
        res = mark(a.week, a.category, a.field, a.value)
    elif a.verb == "plan":
        res = plan(a.week, a.category, a.ranked)
    elif a.verb == "book":
        res = book(a.week, a.category, a.registration_state, a.confirmation, a.screenshot)
    elif a.verb == "skip":
        res = skip(a.week, a.category, a.reason)
    elif a.verb == "cancel":
        res = cancel(a.week, a.category, a.reason)
    elif a.verb == "promote-backup":
        res = promote_backup(a.week, a.category, a.reason)
    elif a.verb == "upcoming":
        res = upcoming()
    elif a.verb == "due":
        res = due(a.kind)
    else:
        assert blank()["status"] == "open"
        res = {"ok": True, "checks": 1, "file": str(c.state_path(FILE))}
    c.out({**res, **c.context_summary()}, exit_code=0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
