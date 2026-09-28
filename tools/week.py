"""Everything the weekly run needs to know before scouting, in one call.

    python3 tools/week.py brief [--week 2026-10-26]
    python3 tools/week.py selftest

Without --week it covers `plan_weeks` from clock.py. It gathers, in compact
form: the calendar entries (local times, no ids, short descriptions), the
evenings blocked by deadlines, current bookings per week, exclusions per
category, the source list per category for the home city (respecting
CURATOR_SOURCE_IDS), and a `busy` list per week ready to hand to the scouts.
It replaces about eight separate tool calls, and its output is a fraction of
the size of the raw calendar listing. It only reads; nothing is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import _common as c

TZ = ZoneInfo("America/New_York")
TOOLS = Path(__file__).resolve().parent


def run(tool: str, *args: str) -> dict:
    r = subprocess.run([sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"ok": False, "error": (r.stderr or r.stdout)[-300:]}


def local(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)


def fmt_day(d: dt.date) -> str:
    return d.strftime("%a %b ") + str(d.day)


def compact_event(e: dict) -> dict:
    desc = re.sub(r"https?://\S+", "", e.get("description") or "")
    desc = " ".join(desc.split())[:100]
    if e.get("all_day"):
        s, en = dt.date.fromisoformat(e["start"][:10]), dt.date.fromisoformat(e["end"][:10]) - dt.timedelta(days=1)
        when = fmt_day(s) + ("" if en <= s else f" to {fmt_day(en)}") + " (all day)"
    else:
        s, en = local(e["start"]), local(e["end"])
        when = f"{fmt_day(s.date())} {s:%H:%M}-{en:%H:%M}"
    out = {"when": when, "title": e.get("summary", "")}
    for k_in, k_out in (("location", "where"), ("calendar", "calendar")):
        if e.get(k_in):
            out[k_out] = e[k_in]
    if e.get("recurring"):
        out["recurring"] = True
    if e.get("curator"):
        out["curator"] = True
    if desc:
        out["note"] = desc
    return out


def brief(weeks: list[dt.date]) -> dict:
    rules = c.load_yaml(c.PROJECT_ROOT / "config" / "rules.yaml")
    cats = [x["id"] for x in rules["categories"] if x.get("per_week", 1)]
    start, end = weeks[0], weeks[-1] + dt.timedelta(days=6)
    cal = run("gcal.py", "list", "--from", start.isoformat(), "--to", end.isoformat())
    blocked = run("deadlines.py", "blocked-evenings", "--from", start.isoformat(), "--to", end.isoformat())
    events = cal.get("events", []) if cal.get("ok", True) else []

    out_weeks = []
    for w in weeks:
        we = w + dt.timedelta(days=6)
        busy = []
        for e in events:
            if e.get("all_day") or e.get("curator"):  # Curator's own bookings stay swappable
                continue
            s, en = local(e["start"]), local(e["end"])
            if w <= s.date() <= we:
                busy.append((s.replace(tzinfo=None), f"{fmt_day(s.date())} {s:%H:%M}-{en:%H:%M}"))
        for b in blocked.get("blocked_evenings", []):
            d = dt.date.fromisoformat(b["date"])
            if w <= d <= we:
                cut = blocked.get("evening_cutoff", "17:00")
                busy.append((dt.datetime.combine(d, dt.time.fromisoformat(cut)), f"{fmt_day(d)} after {cut} (deadline next day)"))
        bk = run("bookings.py", "get", "--week", w.isoformat()).get("bookings", {})
        slots = {}
        for cat in cats:
            r = bk.get(cat)
            if r:
                p = r.get("pick") or {}
                slots[cat] = {k: v for k, v in {"status": r.get("status"), "title": p.get("title"), "start": p.get("start"),
                                                 "speaker_tier": p.get("speaker_tier"), "skip_reason": r.get("skip_reason")}.items() if v}
            else:
                slots[cat] = {"status": "open"}
        out_weeks.append({"start": w.isoformat(), "end": we.isoformat(), "slots": slots,
                          "busy_for_scouts": [t for _, t in sorted(set(busy))]})

    calendar = []
    for e in events:
        if e.get("all_day"):
            s = dt.date.fromisoformat(e["start"][:10])
        else:
            s = local(e["start"]).date()
        calendar.append((s, e.get("all_day", False), compact_event(e)))
    calendar.sort(key=lambda x: (x[0], not x[1]))

    exclusions = {cat: run("memory.py", "exclusions", "--category", cat, "--compact").get("text", "") for cat in cats}

    src = c.load_yaml(c.PROJECT_ROOT / "config" / "sources.yaml")
    city = "fixture" if c.MODE == "fixture" else rules.get("home_city", "Boston")
    override = [x.strip() for x in os.environ.get("CURATOR_SOURCE_IDS", "").split(",") if x.strip()]
    sources = {}
    for cat in cats:
        lst = []
        for s_ in src["cities"].get(city, []):
            if cat not in s_.get("categories", [cat]) or (override and s_["id"] not in override):
                continue
            item = {"id": s_["id"], "url": s_["url"]}
            if s_.get("notes"):
                item["notes"] = s_["notes"]
            lst.append(item)
        sources[cat] = lst

    return {
        "ok": True, "weeks": out_weeks, "categories": cats,
        "calendars_read": cal.get("calendars_read"), "calendar_error": None if cal.get("ok", True) else cal.get("error"),
        "calendar": [e for _, _, e in calendar],
        "blocked_evenings": [{"date": b["date"], "because": b["because"]} for b in blocked.get("blocked_evenings", [])],
        "exclusions": exclusions, "sources_city": city, "sources": sources,
        "source_ids_override": override or None,
        "note": "busy_for_scouts lists timed entries and deadline evenings only; add travel days and days out of town before passing it on.",
        **c.context_summary(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verb", choices=["brief", "selftest"])
    ap.add_argument("--week", help="a Monday; default: plan_weeks from clock.py")
    a = ap.parse_args()
    if a.verb == "brief":
        if a.week:
            weeks = [dt.date.fromisoformat(a.week)]
        else:
            ctx = run("clock.py", "context")
            weeks = [dt.date.fromisoformat(w["start"]) for w in ctx.get("plan_weeks", [])]
        if not weeks:
            c.out({"ok": False, "error": "no weeks to plan"}, exit_code=1)
        result = brief(weeks)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str))
    else:
        e = {"all_day": False, "start": "2026-10-05T12:30:00Z", "end": "2026-10-05T14:00:00Z", "summary": "Class",
             "description": "https://x.y/z  Meeting pattern", "location": "E51"}
        got = compact_event(e)
        assert got["when"] == "Mon Oct 5 08:30-10:00", got
        assert got["note"] == "Meeting pattern", got
        a2 = compact_event({"all_day": True, "start": "2026-10-30", "end": "2026-11-02", "summary": "New York"})
        assert a2["when"] == "Fri Oct 30 to Sun Nov 1 (all day)", a2
        c.out({"ok": True, "checks": 3})


if __name__ == "__main__":
    main()
