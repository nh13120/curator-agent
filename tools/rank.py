"""Hard filters and ranking for verified candidates.

    python3 tools/rank.py rank --candidates <verified json> --week 2026-10-26 [--location-json <file>] [--out <file>]
    python3 tools/rank.py selftest

Applies the filters that need other tools (travel time, calendar free-check,
homework deadlines, travel days), then sorts by the brief's rule: speaker or
artist tier first (a famous speaker always wins), then venue tier, format
tier, taste fit, shorter travel. Returns the pick and the backup with the
reasons, so the main agent records why the winner won.

location-json (optional, produced by the main agent from calendar signals):
  {"home_city": "Boston", "travel_days": ["2026-10-29"], "days": {"2026-10-30": "New York"}, "pending_days": []}
Days not listed are the home city. A pending day is ambiguous: candidates on
it are kept but flagged, never auto-booked.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

import _common as c

AUTO_BOOK = {"free", "free_with_registration", "free_for_students"}
ASK_FIRST = {"suggested_donation", "unclear"}


def read(path: str):
    return json.load(sys.stdin) if path == "-" else c.load_json(c.resolve(path))


def same_city(event_city: str, where: str, rules: dict) -> bool:
    """Cambridge, Somerville and the other home-area towns count as Boston."""
    # "Cambridge, MA" and "Boston, Massachusetts" compare by their first part.
    a, b = c.norm(event_city.split(",")[0]), c.norm(where.split(",")[0])
    if a == b:
        return True
    area = {c.norm(x) for x in rules.get("home_area", [])} | {c.norm(rules.get("home_city", "Boston"))}
    return a in area and b in area


def person_tier(cand: dict) -> int:
    tiers = [p.get("tier", 1) for p in cand.get("speakers", []) + cand.get("artists", [])]
    return max(tiers) if tiers else 1


def assess(cand: dict, rules: dict, location: dict, blocked_evenings: dict, tools: dict) -> dict:
    """Hard filters for one candidate. `tools` holds callables so the selftest can stub them."""
    reasons, flags = [], []
    start, end = c.parse_dt(cand["start"]), c.parse_dt(cand["end"])
    day = start.date().isoformat()
    home = location.get("home_city") or rules.get("home_city", "Boston")
    where = location.get("days", {}).get(day, home)
    away = c.norm(where) != c.norm(home)

    if day in location.get("travel_days", []):
        reasons.append("travel day")
    if day in location.get("pending_days", []):
        flags.append("location for this day is unconfirmed")
    if not same_city(cand.get("city", ""), where, rules):
        reasons.append(f"event is in {cand.get('city')} but Nicolas is in {where} that day")
    if cand.get("price_label") == "paid":
        reasons.append("paid")
    elif cand.get("price_label") in ASK_FIRST:
        flags.append(f"price is {cand['price_label']}: ask first")
    reg_host = urlparse(cand.get("registration_url") or "").hostname or ""
    reg_rules = rules.get("registration") or {}
    if any(reg_host == h or reg_host.endswith("." + h) for h in reg_rules.get("hand_off", [])):
        flags.append(f"registration on {reg_host}: hand off to Nicolas (never attempted by Curator)")
    state = cand.get("registration_state", "open")
    if state in ("full", "waitlist"):
        reasons.append(f"registration {state}")
    elif state == "unclear":
        reasons.append("registration page unclear (treated as full)")
    elif state == "not_open":
        flags.append("registration not open yet: keep and check daily")
    if day in blocked_evenings and start.strftime("%H:%M") > rules.get("evening_cutoff", "17:00"):
        reasons.append(f"evening before a deadline ({blocked_evenings[day]})")
    if away:
        flags.append(f"out of town ({where}): ask first")
        if person_tier(cand) < (rules.get("away") or {}).get("min_speaker_tier", 3):
            reasons.append("away from home and speaker tier below 3")

    travel = tools["travel"](cand.get("venue_address") or cand.get("venue_name", ""))
    travel_min = travel.get("minutes", 30)
    if travel.get("method") == "default_unknown_address":
        flags.append("venue address could not be geocoded; travel time is a default")
    if travel_min > rules.get("max_travel_min", 45):
        reasons.append(f"travel {travel_min} min exceeds {rules.get('max_travel_min', 45)}")
    free = tools["free"](start, end, travel_min)
    if not free.get("ok"):
        flags.append("calendar check failed; not auto-bookable")
    elif not free.get("free"):
        names = [e.get("summary") for e in free.get("conflicts", [])]
        reasons.append(f"calendar conflict with {names}")
    taste = tools["taste"](cand.get("topic_tags", []), cand.get("venue_name", ""), cand.get("format", ""))

    return {**cand, "travel_min": travel_min, "travel_method": travel.get("method"), "taste_fit": taste.get("taste_fit", 3.0),
            "taste_why": taste.get("why", []), "speaker_tier": person_tier(cand), "eligible": not reasons,
            "auto_bookable": not reasons and not flags and cand.get("price_label") in AUTO_BOOK,
            "ineligible_reasons": reasons, "flags": flags}


def sort_key(r: dict):
    return (-r["speaker_tier"], -r.get("venue_tier", 1), -r.get("format_tier", 1), -r["taste_fit"], r["travel_min"])


def rank(cands: list[dict], rules: dict, location: dict, blocked_evenings: dict, tools: dict) -> dict:
    assessed = sorted((assess(cd, rules, location, blocked_evenings, tools) for cd in cands), key=sort_key)
    eligible = [r for r in assessed if r["eligible"]]
    pick = eligible[0] if eligible else None
    backup = next((r for r in eligible[1:] if r["auto_bookable"]), None) if pick else None
    why = None
    if pick:
        why = (f"speaker/artist tier {pick['speaker_tier']}, venue tier {pick.get('venue_tier')}, format tier {pick.get('format_tier')}, "
               f"taste fit {pick['taste_fit']}, travel {pick['travel_min']} min")
        if len(eligible) > 1:
            why += f"; beats {eligible[1]['title']} (tier {eligible[1]['speaker_tier']})"
    # Strong matches while Nicolas is away are offered as questions even when
    # the week's slot is already filled at home (brief: "while I'm away ... only
    # book if there's a strong match; out-of-town events always go to ask-first").
    min_tier = (rules.get("away") or {}).get("min_speaker_tier", 3)
    away_opps = [r for r in eligible if r is not pick and r["speaker_tier"] >= min_tier
                 and any(f.startswith("out of town") for f in r["flags"])]
    return {"ok": True, "pick": pick, "backup": backup, "why": why,
            "away_opportunities": [{"event_id": r["event_id"], "title": r["title"], "start": r["start"], "city": r["city"],
                                    "speaker_tier": r["speaker_tier"], "registration_url": r.get("registration_url"),
                                    "flags": r["flags"]} for r in away_opps],
            "pick_needs_ask": bool(pick and not pick["auto_bookable"]), "pick_flags": pick["flags"] if pick else [],
            "ranked": [{"event_id": r["event_id"], "title": r["title"], "start": r["start"], "speaker_tier": r["speaker_tier"],
                        "venue_tier": r.get("venue_tier"), "format_tier": r.get("format_tier"), "taste_fit": r["taste_fit"],
                        "travel_min": r["travel_min"], "eligible": r["eligible"], "auto_bookable": r["auto_bookable"],
                        "ineligible_reasons": r["ineligible_reasons"], "flags": r["flags"]} for r in assessed],
            "none_eligible_reason": None if pick else "no candidate passes the hard filters"}


def live_tools() -> dict:
    import gcal
    import taste
    import travel

    return {"travel": lambda addr: travel.estimate(addr),
            "free": lambda s, e, t: gcal.free_check(s, e, t, 15),
            "taste": lambda tags, venue, fmt: taste.score(tags, venue, fmt)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("rank"); p.add_argument("--candidates", required=True); p.add_argument("--week", required=True)
    p.add_argument("--location-json"); p.add_argument("--out")
    sub.add_parser("selftest")
    a = ap.parse_args()
    rules = c.load_yaml(c.PROJECT_ROOT / "config" / "rules.yaml", default={}) or {}

    if a.verb == "rank":
        import datetime as dt

        import deadlines

        wk = dt.date.fromisoformat(a.week)
        start, end = wk.isoformat(), (wk + dt.timedelta(days=6)).isoformat()
        dl = deadlines.load()
        blocked = {b["date"]: b["because"] for b in deadlines.blocked_evenings(dl.get("deadlines", []), start, end)}
        location = read(a.location_json) if a.location_json else {}
        res = rank(read(a.candidates), rules, location, blocked, live_tools())
        if a.out:
            c.write_json_atomic(c.resolve(a.out), res)
        c.out({**res, **c.context_summary()})
    else:
        stub = {"travel": lambda addr: {"minutes": 10, "method": "stub"},
                "free": lambda s, e, t: {"ok": True, "free": "busy" not in s.isoformat() and s.hour != 12, "conflicts": [{"summary": "class"}]},
                "taste": lambda tags, v, f: {"taste_fit": 3.0, "why": []}}
        base = {"event_id": "a", "title": "A", "start": "2026-10-29T18:00:00-04:00", "end": "2026-10-29T19:30:00-04:00", "venue_name": "MIT",
                "venue_address": "x", "city": "Cambridge", "speakers": [{"name": "S", "tier": 1}], "artists": [], "topic_tags": [], "format": "lecture",
                "format_tier": 3, "venue_tier": 3, "price_label": "free", "registration_state": "open"}
        t3 = {**base, "event_id": "b", "title": "B tier2", "speakers": [{"name": "F", "tier": 2}]}
        full = {**base, "event_id": "c", "title": "C full", "speakers": [{"name": "G", "tier": 3}], "registration_state": "full"}
        tue = {**base, "event_id": "d", "title": "D deadline eve", "start": "2026-10-27T18:00:00-04:00", "end": "2026-10-27T19:00:00-04:00", "speakers": [{"name": "H", "tier": 3}]}
        nyc = {**base, "event_id": "e", "title": "E NYC", "city": "New York", "start": "2026-10-30T18:00:00-04:00", "end": "2026-10-30T19:00:00-04:00", "speakers": [{"name": "I", "tier": 3}]}
        loc = {"home_city": "Boston", "travel_days": ["2026-10-31"], "days": {"2026-10-30": "New York"}}
        res = rank([base, t3, full, tue, nyc], rules, loc, {"2026-10-27": "HW4"}, stub)
        assert res["pick"]["event_id"] == "e" and res["pick_needs_ask"], "tier-3 in NYC is the pick but must ask first"
        ids = {r["event_id"]: r for r in res["ranked"]}
        assert not ids["c"]["eligible"] and "full" in ids["c"]["ineligible_reasons"][0]
        assert not ids["d"]["eligible"] and "deadline" in ids["d"]["ineligible_reasons"][0]
        assert ids["b"]["auto_bookable"] and res["backup"]["event_id"] == "b"  # Cambridge counts as home (Boston)
        eb = {**base, "event_id": "f", "title": "F eventbrite", "registration_url": "https://www.eventbrite.com/e/x-123", "speakers": [{"name": "J", "tier": 3}]}
        r_eb = rank([eb], rules, loc, {}, stub)
        assert r_eb["pick"]["event_id"] == "f" and r_eb["pick_needs_ask"] and "hand off" in r_eb["pick_flags"][0], r_eb
        res2 = rank([t3, nyc], rules, loc, {}, stub)  # home pick wins on travel; NYC tier-3 still offered
        assert res2["pick"]["event_id"] in ("b", "e") and any(o["event_id"] == "e" for o in res2["away_opportunities"] + ([res2["pick"]] if res2["pick"]["event_id"] == "e" else []))
        c.out({"ok": True, "checks": 6})


if __name__ == "__main__":
    main()
