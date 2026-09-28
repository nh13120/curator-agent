"""Event memory: history, seen candidates, exclusions, ratings.

    python3 tools/memory.py record --event-json <file|-> --status booked [--week 2026-10-26]
    python3 tools/memory.py status --event-id ev_x --status cancelled|skipped|unconfirmed [--note ...]
    python3 tools/memory.py rate   --event-id ev_x --rating 4 [--note "..."]      # confirms attendance
    python3 tools/memory.py seen   --event-json <file|-> --reason past|paid|... [--permanent]
    python3 tools/memory.py exclusions [--category ai] [--compact]
    python3 tools/memory.py history [--status booked] [--category ai] [--since 2026-09-01]
    python3 tools/memory.py show --event-id ev_x
    python3 tools/memory.py selftest

Files (append-only JSONL, latest line per event_id wins):
  memory/history.jsonl  every event booked, attended, skipped, cancelled, unconfirmed
  memory/seen.jsonl     candidates considered and rejected, with the reason

Novelty rules implemented by `exclusions`:
  - a specific event is never recommended again (any status in history)
  - a running exhibition is matched by title + venue whatever the visit date
  - the same speaker giving the same talk is matched by talk_key
  - rejected candidates are excluded only when the reason is permanent
    (past, paid, duplicate_talk, verifier:*) and not for transient ones
    (full, not_open, out_of_window, conflict)
"""

from __future__ import annotations

import argparse
import json
import sys

import _common as c

HISTORY = "memory/history.jsonl"
SEEN = "memory/seen.jsonl"
STATUSES = ("booked", "attended", "unconfirmed", "cancelled", "skipped")
PERMANENT_REASONS = ("past", "paid", "duplicate_talk", "already_seen", "excluded_topic", "excluded_speaker")


def read_event_json(arg: str) -> dict:
    return json.load(sys.stdin) if arg == "-" else c.load_json(c.resolve(arg))


def from_candidate(ev: dict) -> dict:
    """Normalize a candidate/booking record into a history record."""
    date = (ev.get("start") or ev.get("date") or "")[:10]
    venue = ev.get("venue_name") or ev.get("venue") or ""
    speakers = [p["name"] if isinstance(p, dict) else p for p in ev.get("speakers", [])]
    artists = [p["name"] if isinstance(p, dict) else p for p in ev.get("artists", [])]
    return {
        "event_id": ev.get("event_id") or c.event_id(ev["title"], date, venue),
        "title": ev["title"],
        "date": date,
        "end": ev.get("end", ""),
        "venue": venue,
        "venue_address": ev.get("venue_address", ""),
        "city": ev.get("city", ""),
        "speakers": speakers,
        "artists": artists,
        "category": ev.get("category", ""),
        "topic_tags": ev.get("topic_tags", []),
        "format": ev.get("format", ""),
        "source_url": ev.get("event_url") or ev.get("source_url") or "",
        "registration_url": ev.get("registration_url", ""),
        "talk_key": c.talk_key(ev["title"], speakers) if speakers else "",
        "exhibition_key": c.exhibition_key(ev["title"], venue) if ev.get("format") == "exhibition" else "",
    }


def latest_history() -> dict[str, dict]:
    rows = {}
    for r in c.read_jsonl(c.state_path(HISTORY)):
        rows[r["event_id"]] = r
    return rows


def append_history(rec: dict) -> dict:
    rec = {**rec, "updated_at": c.now().isoformat(), "run_id": c.run_id()}
    c.append_jsonl(c.state_path(HISTORY), rec)
    return rec


def record(ev: dict, status: str, week: str | None, rating=None, note=None) -> dict:
    rec = from_candidate(ev)
    rec.update({"status": status, "rating": rating, "note": note, "week": week or c.week_start(c.parse_dt(rec["date"]).date()).isoformat()})
    return append_history(rec)


def set_status(event_id: str, status: str, rating=None, note=None) -> dict:
    prev = latest_history().get(event_id)
    if not prev:
        return {"ok": False, "error": f"unknown event_id {event_id}; use `record` first"}
    rec = {**prev, "status": status}
    if rating is not None:
        rec["rating"] = rating
    if note is not None:
        rec["note"] = note
    return {"ok": True, "record": append_history(rec)}


def rate(event_id: str, rating: int, note: str | None) -> dict:
    """A rating confirms attendance and refreshes the taste summary."""
    if not 1 <= rating <= 5:
        return {"ok": False, "error": "rating must be 1-5"}
    res = set_status(event_id, "attended", rating=rating, note=note)
    if not res["ok"]:
        return res
    import taste

    res["taste"] = taste.regenerate()
    return res


def seen(ev: dict, reason: str, permanent: bool | None) -> dict:
    rec = from_candidate(ev)
    if permanent is None:
        permanent = any(reason.startswith(p) for p in PERMANENT_REASONS) or reason.startswith("verifier:")
    row = {"event_id": rec["event_id"], "title": rec["title"], "date": rec["date"], "venue": rec["venue"],
           "category": rec["category"], "talk_key": rec["talk_key"], "exhibition_key": rec["exhibition_key"],
           "reason": reason, "permanent": permanent, "run_id": c.run_id(), "seen_at": c.now().isoformat()}
    c.append_jsonl(c.state_path(SEEN), row)
    return {"ok": True, "seen": row}


def exclusions(category: str | None) -> list[dict]:
    out = {}
    for r in latest_history().values():
        if category and r.get("category") not in (category, ""):
            continue
        out[r["event_id"]] = {"event_id": r["event_id"], "title": r["title"], "date": r["date"], "venue": r["venue"],
                              "talk_key": r.get("talk_key", ""), "exhibition_key": r.get("exhibition_key", ""),
                              "why": f"history:{r['status']}"}
    for r in c.read_jsonl(c.state_path(SEEN)):
        if not r.get("permanent"):
            continue
        if category and r.get("category") not in (category, ""):
            continue
        out.setdefault(r["event_id"], {"event_id": r["event_id"], "title": r["title"], "date": r["date"], "venue": r["venue"],
                                       "talk_key": r.get("talk_key", ""), "exhibition_key": r.get("exhibition_key", ""),
                                       "why": f"seen:{r['reason']}"})
    return sorted(out.values(), key=lambda x: x["date"])


def is_excluded(ev: dict, excl: list[dict]) -> str | None:
    """Why a candidate is excluded, or None. Used by candidates.py (Phase 5)."""
    rec = from_candidate(ev)
    for x in excl:
        if x["event_id"] == rec["event_id"]:
            return f"same event ({x['why']})"
        if rec["exhibition_key"] and rec["exhibition_key"] == x.get("exhibition_key"):
            return f"same exhibition at the same venue ({x['why']})"
        if rec["talk_key"] and rec["talk_key"] == x.get("talk_key"):
            return f"same speaker, same talk ({x['why']})"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("record"); p.add_argument("--event-json", required=True); p.add_argument("--status", choices=STATUSES, required=True)
    p.add_argument("--week"); p.add_argument("--rating", type=int); p.add_argument("--note")
    p = sub.add_parser("status"); p.add_argument("--event-id", required=True); p.add_argument("--status", choices=STATUSES, required=True)
    p.add_argument("--rating", type=int); p.add_argument("--note")
    p = sub.add_parser("rate"); p.add_argument("--event-id", required=True); p.add_argument("--rating", type=int, required=True); p.add_argument("--note")
    p = sub.add_parser("seen"); p.add_argument("--event-json", required=True); p.add_argument("--reason", required=True)
    p.add_argument("--permanent", action="store_true", default=None)
    p = sub.add_parser("exclusions"); p.add_argument("--category"); p.add_argument("--compact", action="store_true")
    p = sub.add_parser("history"); p.add_argument("--status"); p.add_argument("--category"); p.add_argument("--since")
    p = sub.add_parser("show"); p.add_argument("--event-id", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "record":
        rec = record(read_event_json(a.event_json), a.status, a.week, a.rating, a.note)
        c.out({"ok": True, "record": rec, **c.context_summary()})
    elif a.verb == "status":
        res = set_status(a.event_id, a.status, a.rating, a.note)
        c.out({**res, **c.context_summary()}, exit_code=0 if res["ok"] else 1)
    elif a.verb == "rate":
        res = rate(a.event_id, a.rating, a.note)
        c.out({**res, **c.context_summary()}, exit_code=0 if res["ok"] else 1)
    elif a.verb == "seen":
        c.out({**seen(read_event_json(a.event_json), a.reason, a.permanent), **c.context_summary()})
    elif a.verb == "exclusions":
        rows = exclusions(a.category)
        if a.compact:
            lines = [f"- {r['event_id']} | {r['title']} | {r['date']} | {r['venue']} | {r['why']}" for r in rows]
            c.out({"ok": True, "count": len(rows), "text": "\n".join(lines) or "(none)"})
        else:
            c.out({"ok": True, "count": len(rows), "exclusions": rows, **c.context_summary()})
    elif a.verb == "history":
        rows = [r for r in latest_history().values()
                if (not a.status or r["status"] == a.status) and (not a.category or r["category"] == a.category)
                and (not a.since or r["date"] >= a.since)]
        c.out({"ok": True, "count": len(rows), "history": sorted(rows, key=lambda r: r["date"])})
    elif a.verb == "show":
        rec = latest_history().get(a.event_id)
        c.out({"ok": bool(rec), "record": rec}, exit_code=0 if rec else 1)
    else:
        ev = {"title": "Hokusai: Inspiration and Influence", "start": "2026-10-31T14:00:00-04:00", "venue_name": "Museum of Fine Arts, Boston",
              "format": "exhibition", "artists": [{"name": "Katsushika Hokusai"}], "category": "art"}
        past = {"title": "Hokusai: Inspiration and Influence", "date": "2026-09-12", "venue": "Museum of Fine Arts, Boston",
                "format": "exhibition", "artists": ["Katsushika Hokusai"], "category": "art"}
        excl = [{**from_candidate(past), "why": "history:attended"}]
        assert is_excluded(ev, excl) and "exhibition" in is_excluded(ev, excl)
        talk_a = {"title": "Scaling Laws", "start": "2026-10-01T18:00:00-04:00", "venue_name": "MIT", "speakers": [{"name": "Elena Vasquez"}], "format": "lecture"}
        talk_b = {"title": "Scaling Laws", "start": "2026-11-01T18:00:00-05:00", "venue_name": "Harvard", "speakers": ["Elena Vasquez"], "format": "lecture"}
        assert "same speaker" in (is_excluded(talk_b, [{**from_candidate(talk_a), "why": "history:attended"}]) or "")
        assert is_excluded({"title": "Other", "start": "2026-10-01", "venue_name": "MIT", "format": "talk"}, excl) is None
        c.out({"ok": True, "checks": 3})


if __name__ == "__main__":
    main()
