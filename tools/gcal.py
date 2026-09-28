"""Google Calendar access (read busy times, create/delete Curator events).

    python3 tools/gcal.py list --from 2026-10-26 --to 2026-11-01
    python3 tools/gcal.py free-check --start <iso> --end <iso> --travel-min 20 [--buffer-min 15]
    python3 tools/gcal.py create --title T --start <iso> --end <iso> [--location L] [--description D] [--url U] [--event-id EV]
    python3 tools/gcal.py delete --id <calendar_event_id>
    python3 tools/gcal.py auth          # one-time OAuth (Phase 3)

Modes
  fixture: reads fixtures/cases/<case>/calendar.json plus any events created
           during the run (state/fixture_calendar.json). Writes are simulated.
  dry:     reads the real calendar; create/delete are refused.
  live:    reads and writes the real calendar.

Agent-created events carry the extended private property curator=1 (and the
Curator event id), so they can be found, updated or removed reliably.

Output event shape (all modes):
  {id, summary, start, end, all_day, location, description, recurring, curator}
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import uuid
from pathlib import Path

import _common as c

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRET = c.PROJECT_ROOT / "config" / "google_client_secret.json"
TOKEN_FILE = c.PROJECT_ROOT / "config" / "google_token.json"


# ------------------------------------------------------------------ store ---

def fixture_events() -> list[dict]:
    base = c.load_json(c.fixture_path("calendar.json"), default={"events": []})["events"]
    created = c.load_json(c.state_path("state/fixture_calendar.json"), default={"events": []})["events"]
    return base + created


def google_service():
    """Build the Calendar API client from the saved token. Phase 3 wires the
    one-time browser sign-in (`auth`)."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not TOKEN_FILE.exists():
        raise RuntimeError("Google Calendar not authorized yet: run `python3 tools/gcal.py auth` (Phase 3)")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def calendar_id() -> str:
    """Where Curator WRITES its events."""
    return os.environ.get("CURATOR_GOOGLE_CALENDAR_ID", "primary")


def read_calendar_ids(svc) -> list[tuple[str, str]]:
    """Which calendars Curator READS. Default: every calendar the account has
    selected (classes, travel and imported calendars included), minus holiday
    calendars. Pin the list with CURATOR_GOOGLE_READ_CALENDAR_IDS (comma-separated)."""
    pinned = os.environ.get("CURATOR_GOOGLE_READ_CALENDAR_IDS", "").strip()
    if pinned:
        return [(cid.strip(), cid.strip()) for cid in pinned.split(",") if cid.strip()]
    out = []
    for cal in svc.calendarList().list().execute().get("items", []):
        if "#holiday@" in cal["id"] or not cal.get("selected", False):
            continue
        out.append((cal["id"], cal.get("summary", cal["id"])))
    return out or [("primary", "primary")]


def normalize_google(ev: dict) -> dict:
    start, end = ev.get("start", {}), ev.get("end", {})
    all_day = "date" in start
    props = (ev.get("extendedProperties") or {}).get("private") or {}
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary", ""),
        "start": start.get("date") if all_day else start.get("dateTime"),
        "end": end.get("date") if all_day else end.get("dateTime"),
        "all_day": all_day,
        "location": ev.get("location", ""),
        "description": ev.get("description", ""),
        "recurring": bool(ev.get("recurringEventId")),
        "recurring_event_id": ev.get("recurringEventId"),
        "curator": props.get("curator") == "1",
        "curator_event_id": props.get("curator_event_id"),
    }


# ------------------------------------------------------------------- read ---

def overlaps(ev: dict, start: dt.datetime, end: dt.datetime) -> bool:
    if ev.get("all_day"):
        s = dt.date.fromisoformat(ev["start"][:10])
        e = dt.date.fromisoformat(ev["end"][:10])  # exclusive end, like Google
        return s < end.date() + dt.timedelta(days=1) and e > start.date()
    s, e = c.parse_dt(ev["start"]), c.parse_dt(ev["end"])
    return s < end and e > start


def list_events(start: dt.datetime, end: dt.datetime) -> dict:
    if c.MODE == "fixture":
        rows = [ev for ev in fixture_events() if overlaps(ev, start, end)]
        return {"ok": True, "source": "fixture", "events": sorted(rows, key=lambda e: e["start"])}
    try:
        svc = google_service()
        rows, names = [], []
        for cid, name in read_calendar_ids(svc):
            names.append(name)
            resp = svc.events().list(calendarId=cid, timeMin=start.isoformat(), timeMax=end.isoformat(),
                                     singleEvents=True, orderBy="startTime", maxResults=250).execute()
            for ev in resp.get("items", []):
                n = normalize_google(ev)
                n["calendar"] = name
                rows.append(n)
    except Exception as e:
        return {"ok": False, "error": f"calendar read failed: {e}", "events": []}
    rows.sort(key=lambda e: e["start"])
    return {"ok": True, "source": "google", "calendars_read": names, "write_calendar_id": calendar_id(), "events": rows}


def free_check(start: dt.datetime, end: dt.datetime, travel_min: int, buffer_min: int) -> dict:
    """Is [start-travel-buffer, end+travel+buffer] free of timed calendar
    entries? All-day entries (hotels, 'in NYC') are reported but do not block."""
    pad = dt.timedelta(minutes=travel_min + buffer_min)
    win_s, win_e = start - pad, end + pad
    data = list_events(win_s, win_e)
    if not data["ok"]:
        return data
    timed = [ev for ev in data["events"] if not ev.get("all_day")]
    all_day = [ev for ev in data["events"] if ev.get("all_day")]
    return {"ok": True, "free": not timed, "window": {"start": win_s.isoformat(), "end": win_e.isoformat()},
            "travel_min": travel_min, "buffer_min": buffer_min,
            "conflicts": timed, "all_day_context": all_day, "source": data["source"]}


# ------------------------------------------------------------------ write ---

def maybe_fault() -> None:
    """CURATOR_FAULT=calendar makes the first create of a run fail once (failure tests)."""
    if c.FAULT != "calendar":
        return
    marker = c.state_path("state/.fault_calendar_fired")
    if not marker.exists():
        marker.write_text("1")
        raise RuntimeError("simulated calendar API error (CURATOR_FAULT=calendar)")


def create(title, start, end, location, description, url, curator_event_id) -> dict:
    payload = {"title": title, "start": start, "end": end, "location": location, "url": url}
    try:
        maybe_fault()
    except RuntimeError as e:
        return {"ok": False, "error": f"calendar create failed: {e}", "retryable": True}
    try:
        how = c.require_write("calendar.create", payload)
    except c.ModeBlocked:
        return c.blocked_response("calendar.create", **payload)
    full_desc = (description or "") + (f"\nConfirmation: {url}" if url else "") + "\n\nBooked by Curator."
    if how == "simulated":
        store_path = c.state_path("state/fixture_calendar.json")
        store = c.load_json(store_path, default={"events": []})
        ev = {"id": "fx_" + uuid.uuid4().hex[:10], "summary": title, "start": start, "end": end, "all_day": False,
              "location": location or "", "description": full_desc.strip(), "recurring": False,
              "recurring_event_id": None, "curator": True, "curator_event_id": curator_event_id}
        store["events"].append(ev)
        c.write_json_atomic(store_path, store)
        return {"ok": True, "simulated": True, "event": ev}
    try:
        svc = google_service()
        body = {"summary": title, "location": location or "", "description": full_desc.strip(),
                "start": {"dateTime": start, "timeZone": "America/New_York"},
                "end": {"dateTime": end, "timeZone": "America/New_York"},
                "extendedProperties": {"private": {"curator": "1", "curator_event_id": curator_event_id or ""}}}
        created = svc.events().insert(calendarId=calendar_id(), body=body).execute()
    except Exception as e:
        return {"ok": False, "error": f"calendar create failed: {e}"}
    return {"ok": True, "simulated": False, "event": normalize_google(created)}


def delete(event_id: str) -> dict:
    try:
        how = c.require_write("calendar.delete", {"id": event_id})
    except c.ModeBlocked:
        return c.blocked_response("calendar.delete", id=event_id)
    if how == "simulated":
        store_path = c.state_path("state/fixture_calendar.json")
        store = c.load_json(store_path, default={"events": []})
        before = len(store["events"])
        store["events"] = [e for e in store["events"] if e["id"] != event_id]
        c.write_json_atomic(store_path, store)
        return {"ok": True, "simulated": True, "deleted": before - len(store["events"])}
    try:
        svc = google_service()
        existing = svc.events().get(calendarId=calendar_id(), eventId=event_id).execute()
        if not normalize_google(existing)["curator"]:
            return {"ok": False, "error": "refusing to delete an event Curator did not create"}
        svc.events().delete(calendarId=calendar_id(), eventId=event_id).execute()
    except Exception as e:
        return {"ok": False, "error": f"calendar delete failed: {e}"}
    return {"ok": True, "simulated": False, "deleted": 1}


def auth() -> dict:
    """One-time desktop OAuth. Opens a browser; stores the token (gitignored)."""
    if c.MODE == "fixture":
        return {"ok": False, "error": "auth is not needed in fixture mode"}
    if not CLIENT_SECRET.exists():
        return {"ok": False, "error": f"missing {CLIENT_SECRET.name}: download the OAuth desktop client JSON from Google Cloud Console into config/"}
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return {"ok": True, "token_file": str(TOKEN_FILE), "note": "token stored; it is gitignored"}


# -------------------------------------------------------------------- cli ---

def day_start(s: str) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(s), dt.time.min, tzinfo=c.TZ)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("list"); p.add_argument("--from", dest="start", required=True); p.add_argument("--to", dest="end", required=True)
    p = sub.add_parser("free-check"); p.add_argument("--start", required=True); p.add_argument("--end", required=True)
    p.add_argument("--travel-min", type=int, required=True); p.add_argument("--buffer-min", type=int, default=15)
    p = sub.add_parser("create"); p.add_argument("--title", required=True); p.add_argument("--start", required=True)
    p.add_argument("--end", required=True); p.add_argument("--location", default=""); p.add_argument("--description", default="")
    p.add_argument("--url", default=""); p.add_argument("--event-id", default="")
    p = sub.add_parser("delete"); p.add_argument("--id", required=True)
    sub.add_parser("auth")
    a = ap.parse_args()

    if a.verb == "list":
        res = list_events(day_start(a.start), day_start(a.end) + dt.timedelta(days=1))
    elif a.verb == "free-check":
        res = free_check(c.parse_dt(a.start), c.parse_dt(a.end), a.travel_min, a.buffer_min)
    elif a.verb == "create":
        res = create(a.title, a.start, a.end, a.location, a.description, a.url, a.event_id)
    elif a.verb == "delete":
        res = delete(a.id)
    else:
        res = auth()
    c.out({**res, **c.context_summary()}, exit_code=0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
