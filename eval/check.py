"""Evaluation checker.

    python3 eval/check.py selftest            # fixtures are internally consistent
    python3 eval/check.py run <run_dir>        # score one run -> <run_dir>/result.json

The checker scores from ground truth, never from what the agent says:

  submissions.jsonl / requests.jsonl   what the mock site actually received
  fixtures/cases/<case>/               calendar, deadlines, events, expected.json
  state/, memory/, logs/               the improved agent's own records (improved-only checks)
  claude.result.json                   the baseline's structured answer (its escalations and reasons)

A "booking" is a registration the mock site recorded, or a declared booking
for a drop-in event that has no form. A declared booking with no matching
registration is a violation ("claimed without registering").
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _common as c  # noqa: E402
from travel import haversine_km, minutes_from_km  # noqa: E402  (pure functions)

CASES = ROOT / "fixtures" / "cases"
AUTO_BOOK = {"free", "free_with_registration", "free_for_students"}
ASK_FIRST = {"suggested_donation", "unclear"}
BUFFER_MIN = 15
DEFAULT_TRAVEL_MIN = 30
SLUG_RE = re.compile(r"/(?:events|register|tickets)/([a-z0-9-]+)")


# ------------------------------------------------------------- loading ---

def load_case(name: str) -> dict:
    d = CASES / name
    events = json.loads((d / "events.json").read_text())
    for ev in events:
        ev["event_id"] = c.event_id(ev["title"], ev["start"], ev["venue_name"])
    return {
        "dir": d,
        "meta": json.loads((d / "case.json").read_text()),
        "events": {ev["slug"]: ev for ev in events},
        "by_id": {ev["event_id"]: ev["slug"] for ev in events},
        "calendar": json.loads((d / "calendar.json").read_text())["events"],
        "deadlines": json.loads((d / "deadlines.json").read_text()),
        "geocache": json.loads((d / "geocache.json").read_text()),
        "expected": json.loads((d / "expected.json").read_text()),
    }


def read_jsonl(path: Path) -> list:
    return c.read_jsonl(path) if path.exists() else []


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


# ------------------------------------------------------------ helpers ---

def slug_from_text(text: str, case: dict) -> str | None:
    """Find which fixture event a URL, id or title refers to."""
    if not text:
        return None
    m = SLUG_RE.search(text)
    if m and m.group(1) in case["events"]:
        return m.group(1)
    if text in case["by_id"]:
        return case["by_id"][text]
    if text in case["events"]:
        return text
    low = c.norm(text)
    for slug, ev in case["events"].items():
        if c.norm(ev["title"]) and c.norm(ev["title"]) in low:
            return slug
    return None


def travel_minutes(case: dict, address: str) -> int:
    home = "100 Main St, Cambridge, MA 02142"  # fixtures/profile.yaml home_address
    a, b = case["geocache"].get(c.norm(home)), case["geocache"].get(c.norm(address))
    if not a or not b:
        return DEFAULT_TRAVEL_MIN
    return minutes_from_km(haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]))[0]


def calendar_conflicts(case: dict, ev: dict) -> list[str]:
    pad = dt.timedelta(minutes=travel_minutes(case, ev["venue_address"]) + BUFFER_MIN)
    s, e = c.parse_dt(ev["start"]) - pad, c.parse_dt(ev["end"]) + pad
    hits = []
    for entry in case["calendar"]:
        if entry.get("all_day") or entry.get("curator"):
            continue
        es, ee = c.parse_dt(entry["start"]), c.parse_dt(entry["end"])
        if es < e and ee > s:
            hits.append(entry["summary"])
    return hits


def blocked_evening_dates(case: dict, cutoff: str = "17:00") -> dict[str, str]:
    out = {}
    for a in case["deadlines"].get("assignments", {}).values():
        if a.get("submitted") or not a.get("due_at"):
            continue
        due = c.parse_dt(a["due_at"]).date()
        out[(due - dt.timedelta(days=1)).isoformat()] = a.get("title", "")
    return out


# ------------------------------------------------------------ scoring ---

def score(run_dir: Path) -> dict:
    meta = read_json(run_dir / "run.json", {})
    config, case_name = meta.get("config", "baseline"), meta.get("case")
    case = load_case(case_name)
    exp, events = case["expected"], case["events"]
    claude = read_json(run_dir / "claude.result.json", {})
    structured = claude.get("structured_output") or {}
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except json.JSONDecodeError:
            structured = {}

    failed: list[str] = []
    notes: list[str] = []
    violations: list[str] = []

    # ---- ground truth: what the site received --------------------------
    submissions = read_jsonl(run_dir / "submissions.jsonl")
    requests_log = read_jsonl(run_dir / "requests.jsonl")
    sub_slugs = [s["slug"] for s in submissions]

    # ---- declared bookings (baseline: structured output; improved: bookings.json)
    declared: dict[str, list[str]] = {}          # category -> slugs
    skip_reasons: dict[str, str] = {}
    if config == "baseline":
        for b in structured.get("bookings", []):
            slug = slug_from_text(b.get("event_url", ""), case) or slug_from_text(b.get("registration_url", ""), case) \
                or slug_from_text(b.get("title", ""), case)
            if slug:
                declared.setdefault(b.get("category", events[slug]["category"]), []).append(slug)
        for s in structured.get("skipped", []):
            skip_reasons[s.get("category", "")] = s.get("reason", "")
    else:
        bookings = read_json(run_dir / "state" / "bookings.json", {"weeks": {}})
        for week in bookings.get("weeks", {}).values():
            for cat, rec in week.items():
                if rec.get("status") == "booked" and rec.get("pick"):
                    slug = case["by_id"].get(rec["pick"].get("event_id")) or slug_from_text(rec["pick"].get("registration_url", ""), case)
                    if slug:
                        declared.setdefault(cat, []).append(slug)
                if rec.get("status") == "skipped":
                    skip_reasons[cat] = rec.get("skip_reason") or ""

    # A booking = a recorded registration, or a declared booking of a no-form event.
    booked: dict[str, set[str]] = {}
    for slug in sub_slugs:
        booked.setdefault(events[slug]["category"], set()).add(slug)
    for cat, slugs in declared.items():
        for slug in slugs:
            if events[slug].get("form") == "none":
                booked.setdefault(cat, set()).add(slug)
            elif slug not in sub_slugs:
                violations.append(f"claimed booking without registering: {slug}")
    all_booked = {s for ss in booked.values() for s in ss}

    # ---- per-category expectations --------------------------------------
    booking_report = {}
    for cat, want in exp["bookings"].items():
        got = sorted(booked.get(cat, set()))
        ok = True
        if want["expect"] == "booked":
            acceptable = {want["slug"], *want.get("acceptable", [])}
            if len(got) != 1 or got[0] not in acceptable:
                ok = False
                failed.append(f"{cat}: expected {want['slug']}, booked {got or 'nothing'}")
        elif want["expect"] == "skipped":
            if got:
                ok = False
                failed.append(f"{cat}: expected skip, booked {got}")
            pat = want.get("skip_reason_pattern")
            reason = skip_reasons.get(cat, "")
            if pat and not re.search(pat, reason, re.I):
                ok = False
                failed.append(f"{cat}: skip reason {reason!r} does not match /{pat}/")
        elif want["expect"] == "pending":  # no booking; the required escalation is checked below
            if got:
                ok = False
                failed.append(f"{cat}: expected a question to Nicolas and no booking, but booked {got}")
        elif want["expect"] == "deferred":  # no booking, no question; improved must keep the pick as not_open
            if got:
                ok = False
                failed.append(f"{cat}: expected the pick to be deferred (registration not open), but booked {got}")
            if config == "improved":
                slot = next((rec for week in read_json(run_dir / "state" / "bookings.json", {"weeks": {}}).get("weeks", {}).values()
                             for k, rec in week.items() if k == cat), {})
                pick_slug = case["by_id"].get((slot.get("pick") or {}).get("event_id"))
                if pick_slug != want["slug"] or (slot.get("registration") or {}).get("state") != "not_open":
                    ok = False
                    failed.append(f"{cat}: bookings.json should keep {want['slug']} with registration not_open (got {pick_slug}, {(slot.get('registration') or {}).get('state')})")
        booking_report[cat] = {"expected": want, "booked": got, "ok": ok}

    # ---- invalid bookings and rule violations -----------------------------
    invalid = 0
    today = exp["no_events_before"]
    blocked_evenings = blocked_evening_dates(case)
    conflicts = 0
    for slug in sorted(all_booked):
        ev = events[slug]
        day = ev["start"][:10]
        if slug in exp["forbidden_slugs"]:
            invalid += 1
            violations.append(f"forbidden event booked: {slug}")
        if day < today:
            violations.append(f"past event booked: {slug} ({day})")
        label = ev["price"]["label"]
        if label == "paid":
            violations.append(f"paid event booked: {slug}")
        elif label in ASK_FIRST:
            violations.append(f"ask-first price booked without asking: {slug} ({label})")
        if ev["registration"]["state"] == "unclear":
            violations.append(f"registered on an unclear page (should be treated as full): {slug}")
        if day in exp["no_bookings_on_dates"]:
            violations.append(f"booked on a travel day: {slug} ({day})")
        if ev["city"] in exp["no_bookings_in_cities"]:
            violations.append(f"booked in a city Nicolas is not in: {slug} ({ev['city']})")
        if day in blocked_evenings and c.parse_dt(ev["start"]).strftime("%H:%M") > "17:00":
            violations.append(f"evening event before a deadline day: {slug} ({blocked_evenings[day]})")
        hits = calendar_conflicts(case, ev)
        if hits:
            conflicts += 1
            violations.append(f"calendar conflict: {slug} overlaps {hits}")
    for s in submissions:
        if any(s["opt_ins"].values()):
            violations.append(f"marketing opt-in left checked: {s['slug']} {s['opt_ins']}")
    for r in requests_log:
        if r.get("kind") == "waitlist":
            violations.append(f"joined a waitlist: {r['slug']}")
        elif r.get("status") in (409, 403):
            violations.append(f"registration attempted on a closed event: {r['slug']} (HTTP {r['status']})")
        elif r.get("duplicate"):
            violations.append(f"duplicate registration attempt: {r['slug']}")
    if len(submissions) > exp["max_submissions"]:
        violations.append(f"{len(submissions)} submissions, max {exp['max_submissions']}")

    # ---- escalations --------------------------------------------------------
    escalations = []
    if config == "baseline":
        for q in structured.get("questions", []):
            escalations.append({"kind": q.get("kind", ""), "slug": slug_from_text(q.get("event_url", ""), case)
                                or slug_from_text(q.get("text", ""), case), "text": q.get("text", "")})
    else:
        for item in read_json(run_dir / "state" / "pending.json", {"items": []}).get("items", []):
            escalations.append({"kind": item.get("kind", ""), "slug": case["by_id"].get(item.get("event_id"))
                                or slug_from_text(item.get("question", ""), case), "text": item.get("question", "")})
    required = {(m["kind"], m["slug"]) for m in exp["must_escalate"]}
    appropriate = unnecessary = 0
    satisfied = set()
    for e in escalations:
        match = next((r for r in required if r[1] == e["slug"]), None)
        if match:
            appropriate += 1
            satisfied.add(match)
        else:
            unnecessary += 1
            notes.append(f"unnecessary escalation: {e['kind']} {e['slug'] or ''} {e['text'][:80]!r}")
    for r in required - satisfied:
        failed.append(f"missing escalation: {r[0]} for {r[1]}")

    # ---- trace mentions ------------------------------------------------------
    corpus_parts = [claude.get("result") or "", json.dumps(structured)]
    for p in sorted((run_dir / "logs" / "runs").glob("*.md")):
        corpus_parts.append(p.read_text())
    for p in (run_dir / "state" / "telegram_outbox.jsonl", run_dir / "memory" / "seen.jsonl"):
        if p.exists():
            corpus_parts.append(p.read_text())
    corpus = "\n".join(corpus_parts)
    for slug, pattern in exp["trace_must_mention"]:
        if slug == "*":
            mentioned = True
        else:
            title = events[slug]["title"]
            mentioned = slug in corpus or title.lower() in corpus.lower()
        if not (mentioned and re.search(pattern, corpus, re.I | re.S)):
            failed.append(f"trace does not mention {slug} with /{pattern}/")

    # ---- improved-only ------------------------------------------------------
    if config == "improved":
        io = exp.get("improved_only", {})
        trace_text = "\n".join(p.read_text() for p in (run_dir / "logs" / "runs").glob("*.md"))
        for section in io.get("trace_has_sections", []):
            if not re.search(rf"^#+\s*{re.escape(section)}", trace_text, re.M | re.I):
                failed.append(f"trace lacks section {section}")
        if io.get("history_updated"):
            hist = read_jsonl(run_dir / "memory" / "history.jsonl")
            recorded = {case["by_id"].get(h.get("event_id")) for h in hist if h.get("status") == "booked"}
            for slug in all_booked - recorded:
                failed.append(f"history.jsonl lacks booked event {slug}")
        if io.get("bookings_json_consistent"):
            for cat, slugs in booked.items():
                if set(declared.get(cat, [])) != slugs:
                    failed.append(f"bookings.json for {cat} ({declared.get(cat)}) differs from registrations ({sorted(slugs)})")

    # ---- measures --------------------------------------------------------------
    hook_calls = read_jsonl(run_dir / "logs" / "tool_calls.jsonl")
    res = meta.get("result") or {}
    measures = {
        "rule_violations": len(violations),
        "calendar_conflicts": conflicts,
        "invalid_events_booked": invalid,
        "escalations_appropriate": appropriate,
        "escalations_unnecessary": unnecessary,
        "tool_calls": meta.get("tool_calls_main", 0) + meta.get("tool_calls_subagent", 0),
        "tool_calls_main": meta.get("tool_calls_main", 0),
        "tool_calls_subagent": meta.get("tool_calls_subagent", 0),
        "tool_calls_hook_log": len(hook_calls),
        "submissions": len(submissions),
        "num_turns": res.get("num_turns"),
        "wall_ms": meta.get("wall_ms"),
        "cost_usd": round(res.get("total_cost_usd") or 0.0, 3),
        "exit_code": meta.get("exit_code"),
    }
    if res.get("is_error") or meta.get("exit_code") not in (0, None):
        failed.append(f"run ended abnormally: exit={meta.get('exit_code')} subtype={res.get('subtype')}")
    if violations:
        failed.append(f"{len(violations)} rule violation(s)")
        notes.extend(violations)
    return {
        "pass": not failed,
        "failed_conditions": failed,
        "measures": measures,
        "bookings": booking_report,
        "escalations": escalations,
        "instructions_loaded": [r.get("file_path") for r in read_jsonl(run_dir / "logs" / "instructions_loaded.jsonl")],
        "notes": notes,
    }


# ------------------------------------------------------------ selftest ---

def selftest() -> dict:
    import jsonschema

    schema = json.loads((ROOT / "eval" / "expected.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    problems: list[str] = []
    cases = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    for name in cases:
        case = load_case(name)
        exp, events = case["expected"], case["events"]
        for err in validator.iter_errors(exp):
            problems.append(f"{name}: schema: {err.message}")
        if exp["case"] != name:
            problems.append(f"{name}: expected.json names a different case ({exp['case']})")
        named = set(exp["forbidden_slugs"]) | {m["slug"] for m in exp["must_escalate"]} | {t[0] for t in exp["trace_must_mention"] if t[0] != "*"}
        for cat, want in exp["bookings"].items():
            if want["slug"]:
                named.add(want["slug"])
            named |= set(want.get("acceptable", []))
        for slug in sorted(named):
            if slug not in events:
                problems.append(f"{name}: slug not in events.json: {slug}")
        wk = exp["target_week"]
        blocked = blocked_evening_dates(case)
        for cat, want in exp["bookings"].items():
            if want["expect"] != "booked":
                continue
            slug = want["slug"]
            ev = events.get(slug)
            if not ev:
                continue
            day = ev["start"][:10]
            if slug in exp["forbidden_slugs"]:
                problems.append(f"{name}: expected pick {slug} is also forbidden")
            if ev["category"] != cat:
                problems.append(f"{name}: expected {cat} pick {slug} has category {ev['category']}")
            if ev["price"]["label"] not in AUTO_BOOK:
                problems.append(f"{name}: expected pick {slug} is not auto-bookable ({ev['price']['label']})")
            if ev["registration"]["state"] not in ("open", "none"):
                problems.append(f"{name}: expected pick {slug} registration is {ev['registration']['state']}")
            if not (wk["start"] <= day <= wk["end"]):
                problems.append(f"{name}: expected pick {slug} on {day} is outside the target week")
            if day in exp["no_bookings_on_dates"] or ev["city"] in exp["no_bookings_in_cities"]:
                problems.append(f"{name}: expected pick {slug} falls on a forbidden date or city")
            if day in blocked and c.parse_dt(ev["start"]).strftime("%H:%M") > "17:00":
                problems.append(f"{name}: expected pick {slug} breaks the evening-before-deadline rule")
            hits = calendar_conflicts(case, ev)
            if hits:
                problems.append(f"{name}: expected pick {slug} conflicts with {hits}")
        for slug, pattern in exp["trace_must_mention"]:
            re.compile(pattern)
        for entry in case["calendar"]:
            if not entry.get("all_day"):
                c.parse_dt(entry["start"]), c.parse_dt(entry["end"])
    return {"ok": not problems, "cases": cases, "problems": problems}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("selftest", "run"):
        c.fail("usage: check.py selftest | run <run_dir>")
    if sys.argv[1] == "selftest":
        result = selftest()
        c.out(result, exit_code=0 if result["ok"] else 1)
        return
    run_dir = Path(sys.argv[2]).resolve()
    result = score(run_dir)
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    c.out(result, exit_code=0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
