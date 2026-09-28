"""Candidate pipeline between the scout, the verifier and the main agent.

    python3 tools/candidates.py save --category ai --stage raw|verdicts <<'EOF'   (JSON on stdin)
    python3 tools/candidates.py validate --input <scout json> --category ai --window 2026-10-26..2026-11-01 --out <kept json>
    python3 tools/candidates.py for-verifier --candidates <kept json> [--out <file>]
    python3 tools/candidates.py apply-verdicts --candidates <kept json> --verdicts <verifier json> --out <verified json>
    python3 tools/candidates.py intake --category ai --window 2026-10-26..2026-11-01
    python3 tools/candidates.py finish --category ai --week 2026-10-26 --location-json - <<< '<location json>'
    python3 tools/candidates.py selftest

intake         save is done by the SubagentStop hook (tools/hooks/save_subagent.py);
               intake = validate + for-verifier in one call, on the reply the hook
               saved in this run.
finish         apply-verdicts + rank.py in one call, on the verifier reply the hook
               saved in this run.

validate       The main agent's check on the scout's work, before anything else:
               JSON-schema validation, then semantic rules that need no web
               access. Dropped candidates are written to memory/seen.jsonl with
               the reason. `retry_needed` is true when nothing survived, which
               is the signal to ask the scout again (at most 2 retries).
for-verifier   Strips the scout's reasoning (notes, price quotes) so the
               verifier's check is independent.
apply-verdicts Keeps passing candidates, records failures in seen.jsonl as
               verifier:<check>, and copies observed price/state corrections.
               A candidate that failed ONLY on price label and/or registration
               state is kept with the values the verifier saw on the page;
               rank.py then applies the rules to those values (paid excluded,
               unclear price asks first, full/waitlist/unclear is not bookable).
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import _common as c
import memory

SCHEMA = c.PROJECT_ROOT / "config" / "schemas" / "candidates.schema.json"
PRICE_LABELS = ("free", "free_with_registration", "free_for_students", "suggested_donation", "paid", "unclear")
REG_STATES = ("open", "full", "waitlist", "not_open", "unclear", "none")
FIXABLE = {"price_label_ok": ("price_label", PRICE_LABELS), "registration_state_ok": ("registration_state", REG_STATES)}
VERIFIER_FIELDS = ("event_id", "title", "start", "end", "venue_name", "venue_address", "city", "category",
                   "price_label", "registration_state", "event_url", "registration_url",
                   "speakers", "artists", "venue_tier", "venue_evidence_url", "format")


def read(path: str):
    if path == "-":
        return json.load(sys.stdin)
    data = c.load_json(c.resolve(path))
    if data is None:
        raise SystemExit(json.dumps({"ok": False, "error": f"file not found: {c.resolve(path)}"}))
    return data


def write(path: str | None, obj) -> None:
    if path:
        c.write_json_atomic(c.resolve(path), obj)


def save(category: str, stage: str, text: str) -> dict:
    """Store a subagent's JSON reply (piped on stdin) under state/candidates/.
    The main agent never writes files itself; this keeps every run's state in
    one place and rejects replies that are not JSON."""
    text = text.strip()
    if text.startswith("```"):  # tolerate a fenced code block around the JSON
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"reply is not valid JSON: {e}", "path": None}
    path = c.resolve(f"state/candidates/{category}.{stage}.json")
    c.write_json_atomic(path, obj)
    return {"ok": True, "path": str(path), "top_level_keys": sorted(obj.keys()) if isinstance(obj, dict) else "list"}


def schema_errors(raw: dict) -> list[str]:
    import jsonschema

    schema = c.load_json(SCHEMA)
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in v.iter_errors(raw)][:20]


def validate(raw: dict, category: str, window: tuple[str, str], rules: dict, record_seen: bool = True) -> dict:
    errs = schema_errors(raw)
    if errs:
        return {"ok": False, "schema_errors": errs, "kept": [], "dropped": [], "retry_needed": True}
    excl = memory.exclusions(category)
    ex_rules = rules.get("exclusions") or {}
    kept, dropped = [], []
    today = c.now().date().isoformat()

    def drop(cand: dict, reason: str, permanent: bool | None = None) -> None:
        dropped.append({"title": cand.get("title"), "start": cand.get("start"), "reason": reason})
        if record_seen:
            memory.seen(cand, reason, permanent)

    for cand in raw.get("candidates", []):
        try:
            start = c.parse_dt(cand["start"])
            c.parse_dt(cand["end"])
        except Exception:
            drop(cand, "unparseable date")
            continue
        day = start.date().isoformat()
        cand = dict(cand)
        cand["event_id"] = c.event_id(cand["title"], day, cand["venue_name"])
        if cand.get("category") != category:
            drop(cand, f"wrong category ({cand.get('category')})")
            continue
        if day < today:
            drop(cand, "past", permanent=True)
            continue
        if not (window[0] <= day <= window[1]):
            drop(cand, "out_of_window", permanent=False)
            continue
        if cand.get("price_label") == "paid":
            drop(cand, "paid", permanent=True)
            continue
        why = memory.is_excluded(cand, excl)
        if why:
            drop(cand, f"already_seen: {why}", permanent=True)
            continue
        low_text = c.norm(" ".join([cand.get("title", ""), " ".join(cand.get("topic_tags", []))]))
        hit = next((t for t in ex_rules.get("topics", []) if c.norm(t) in low_text), None)
        if hit:
            drop(cand, f"excluded_topic: {hit}", permanent=True)
            continue
        names = [p.get("name", "") for p in cand.get("speakers", []) + cand.get("artists", [])]
        hit = next((s for s in ex_rules.get("speakers", []) if any(c.norm(s) == c.norm(n) for n in names)), None)
        if hit:
            drop(cand, f"excluded_speaker: {hit}", permanent=True)
            continue
        if any(c.norm(v) == c.norm(cand.get("venue_name", "")) for v in ex_rules.get("venues", [])):
            drop(cand, "excluded_venue", permanent=True)
            continue
        # Tiers without evidence are tier 1, whatever the scout said.
        downgrades = []
        for p in cand.get("speakers", []) + cand.get("artists", []):
            if p.get("tier", 1) > 1 and not p.get("evidence_url"):
                downgrades.append(p["name"])
                p["tier"] = 1
        if cand.get("venue_tier", 1) > 1 and not cand.get("venue_evidence_url"):
            cand["venue_tier"] = 1
            downgrades.append("venue")
        if downgrades:
            cand["notes"] = (cand.get("notes", "") + f" | tier downgraded to 1 (no evidence): {downgrades}").strip(" |")
        kept.append(cand)
    return {"ok": True, "schema_errors": [], "kept": kept, "dropped": dropped, "retry_needed": not kept,
            "exhausted": raw.get("exhausted", False), "scout_notes": raw.get("notes", "")}


def for_verifier(cands: list[dict]) -> list[dict]:
    out = []
    for cand in cands:
        rec = {k: cand.get(k) for k in VERIFIER_FIELDS}
        rec["speakers"] = [{"name": p.get("name"), "tier": p.get("tier", 1), "evidence_url": p.get("evidence_url", "")} for p in cand.get("speakers", [])]
        rec["artists"] = [{"name": p.get("name"), "tier": p.get("tier", 1), "evidence_url": p.get("evidence_url", "")} for p in cand.get("artists", [])]
        out.append(rec)
    return out


def apply_verdicts(cands: list[dict], verdicts: dict, record_seen: bool = True) -> dict:
    by_id = {v["event_id"]: v for v in verdicts.get("results", [])}
    passed, failed = [], []
    for cand in cands:
        v = by_id.get(cand["event_id"])
        if not v:
            failed.append({"title": cand["title"], "reason": "verifier returned no verdict"})
            if record_seen:
                memory.seen(cand, "verifier:no_verdict", permanent=False)
            continue
        if v.get("verdict") == "pass":
            obs = v.get("observed") or {}
            for key in ("price_label", "registration_state"):
                if obs.get(key) and obs[key] != cand.get(key):
                    cand.setdefault("corrections", {})[key] = {"scout": cand.get(key), "verifier": obs[key]}
                    cand[key] = obs[key]
            cand["verified"] = True
            passed.append(cand)
        else:
            bad = [k for k, ok in (v.get("checks") or {}).items() if ok is False]
            obs = v.get("observed") or {}
            if bad and set(bad) <= set(FIXABLE) and all(obs.get(FIXABLE[k][0]) in FIXABLE[k][1] for k in bad):
                # Only a label the verifier read differently: take the page's value, let rank.py judge it.
                for k in bad:
                    key = FIXABLE[k][0]
                    cand.setdefault("corrections", {})[key] = {"scout": cand.get(key), "verifier": obs[key]}
                    cand[key] = obs[key]
                cand["verified"] = True
                cand["verified_with_corrections"] = [FIXABLE[k][0] for k in bad]
                passed.append(cand)
                continue
            reason = "verifier:" + (",".join(bad) or "fail")
            failed.append({"title": cand["title"], "event_id": cand["event_id"], "reason": reason, "detail": v.get("reason", "")})
            if record_seen:
                permanent = bool({"not_past", "tier_evidence_ok"} & set(bad))
                memory.seen(cand, reason, permanent=permanent)
    return {"ok": True, "passed": passed, "failed": failed, "retry_needed": not passed}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("save"); p.add_argument("--category", required=True); p.add_argument("--stage", required=True, choices=["raw", "verdicts"])
    p = sub.add_parser("validate"); p.add_argument("--input", required=True); p.add_argument("--category", required=True)
    p.add_argument("--window", required=True, help="YYYY-MM-DD..YYYY-MM-DD"); p.add_argument("--out")
    p = sub.add_parser("for-verifier"); p.add_argument("--candidates", required=True); p.add_argument("--out")
    p = sub.add_parser("apply-verdicts"); p.add_argument("--candidates", required=True); p.add_argument("--verdicts", required=True); p.add_argument("--out")
    p = sub.add_parser("intake"); p.add_argument("--category", required=True); p.add_argument("--window", required=True, help="YYYY-MM-DD..YYYY-MM-DD")
    p = sub.add_parser("finish"); p.add_argument("--category", required=True); p.add_argument("--week", required=True)
    p.add_argument("--location-json", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    rules = c.load_yaml(c.PROJECT_ROOT / "config" / "rules.yaml", default={}) or {}

    if a.verb == "save":
        res = save(a.category, a.stage, sys.stdin.read())
        c.out({**res, **c.context_summary()}, exit_code=0 if res["ok"] else 1)
    elif a.verb == "validate":
        start, end = a.window.split("..")
        raw = read(a.input)
        res = validate(raw, a.category, (start, end), rules)
        write(a.out, res["kept"])
        summary = {**res, "kept": [{"event_id": k["event_id"], "title": k["title"], "start": k["start"]} for k in res["kept"]],
                   "kept_file": a.out, "kept_count": len(res["kept"])}
        c.out({**summary, **c.context_summary()}, exit_code=0 if res["ok"] else 1)
    elif a.verb in ("intake", "finish"):
        cat = a.category
        stage = "raw" if a.verb == "intake" else "verdicts"
        meta = c.load_json(c.resolve(f"state/candidates/{cat}.{stage}.meta.json"), default={}) or {}
        if meta.get("run_id") != c.run_id():
            c.out({"ok": False, "error": f"no {stage} reply for '{cat}' was saved by the hook in this run; save it with "
                   f"`candidates.py save --category {cat} --stage {stage} <<< '<json>'`, then use the separate verbs", **c.context_summary()}, exit_code=1)
        if a.verb == "intake":
            start, end = a.window.split("..")
            res = validate(read(f"state/candidates/{cat}.raw.json"), cat, (start, end), rules)
            write(f"state/candidates/{cat}.kept.json", res["kept"])
            recs = for_verifier(res["kept"])
            c.out({"ok": res["ok"], "schema_errors": res["schema_errors"], "dropped": res["dropped"], "retry_needed": res["retry_needed"],
                   "exhausted": res["exhausted"], "scout_notes": res["scout_notes"], "kept_count": len(res["kept"]),
                   "kept_file": f"state/candidates/{cat}.kept.json", "verifier_records": recs, **c.context_summary()},
                  exit_code=0 if res["ok"] else 1)
        else:
            import datetime as dt

            import deadlines
            import rank as rk

            res = apply_verdicts(read(f"state/candidates/{cat}.kept.json"), read(f"state/candidates/{cat}.verdicts.json"))
            write(f"state/candidates/{cat}.verified.json", res["passed"])
            wk = dt.date.fromisoformat(a.week)
            start, end = wk.isoformat(), (wk + dt.timedelta(days=6)).isoformat()
            dl = deadlines.load()
            blocked = {b["date"]: b["because"] for b in deadlines.blocked_evenings(dl.get("deadlines", []), start, end)}
            ranked = rk.rank(res["passed"], rules, read(a.location_json), blocked, rk.live_tools())
            write(f"state/candidates/{cat}.ranked.json", ranked)
            c.out({"ok": True, "verified": [{"event_id": k["event_id"], "title": k["title"], "corrected": k.get("verified_with_corrections")}
                                            for k in res["passed"]],
                   "failed": res["failed"], "retry_needed": res["retry_needed"], "ranked_file": f"state/candidates/{cat}.ranked.json",
                   **ranked, **c.context_summary()})
    elif a.verb == "for-verifier":
        out = for_verifier(read(a.candidates))
        write(a.out, out)
        c.out({"ok": True, "count": len(out), "candidates": out, "file": a.out})
    elif a.verb == "apply-verdicts":
        res = apply_verdicts(read(a.candidates), read(a.verdicts))
        write(a.out, res["passed"])
        c.out({**res, "passed": [{"event_id": k["event_id"], "title": k["title"]} for k in res["passed"]],
               "passed_file": a.out, **c.context_summary()})
    else:
        base = {"title": "T", "start": "2026-10-29T18:00:00-04:00", "end": "2026-10-29T19:30:00-04:00", "venue_name": "MIT",
                "venue_address": "a", "city": "Boston", "speakers": [{"name": "X", "tier": 3, "evidence_url": ""}], "artists": [],
                "category": "ai", "topic_tags": ["crypto"], "format": "talk", "format_tier": 3, "price_label": "free",
                "price_evidence": "", "event_url": "u", "registration_url": "u", "registration_state": "open",
                "venue_tier": 3, "venue_evidence_url": "v", "source_id": "s"}
        raw = {"category": "ai", "city": "Boston", "window": {"start": "2026-10-26", "end": "2026-11-01"}, "sources_checked": [], "exhausted": False,
               "candidates": [base, {**base, "title": "Past", "start": "2026-09-01T18:00:00-04:00", "end": "2026-09-01T19:00:00-04:00"},
                              {**base, "title": "Paid", "price_label": "paid"}]}
        res = validate(raw, "ai", ("2026-10-26", "2026-11-01"), {"exclusions": {"topics": [], "speakers": [], "venues": []}}, record_seen=False)
        assert [d["reason"] for d in res["dropped"]] == ["past", "paid"], res["dropped"]
        assert res["kept"][0]["speakers"][0]["tier"] == 1, "tier without evidence must become 1"
        res2 = validate(raw, "ai", ("2026-10-26", "2026-11-01"), {"exclusions": {"topics": ["crypto"], "speakers": [], "venues": []}}, record_seen=False)
        assert res2["retry_needed"] and any("excluded_topic" in d["reason"] for d in res2["dropped"])
        assert schema_errors({"category": "ai"})  # missing required keys
        av = apply_verdicts([{**base, "event_id": "e1"}], {"results": [{"event_id": "e1", "verdict": "fail", "checks": {"not_past": False}}]}, record_seen=False)
        assert av["failed"][0]["reason"] == "verifier:not_past" and av["retry_needed"]
        av2 = apply_verdicts([{**base, "event_id": "e2"}], {"results": [{"event_id": "e2", "verdict": "fail",
              "checks": {"price_label_ok": False, "registration_state_ok": False}, "observed": {"price_label": "free_with_registration", "registration_state": "unclear"}}]}, record_seen=False)
        p2 = av2["passed"][0]
        assert p2["price_label"] == "free_with_registration" and p2["registration_state"] == "unclear" and p2["verified_with_corrections"], av2
        av3 = apply_verdicts([{**base, "event_id": "e3"}], {"results": [{"event_id": "e3", "verdict": "fail",
              "checks": {"registration_state_ok": False, "tier_evidence_ok": False}, "observed": {"registration_state": "none"}}]}, record_seen=False)
        assert not av3["passed"], "a failed evidence check is never corrected away"
        av4 = apply_verdicts([{**base, "event_id": "e4"}], {"results": [{"event_id": "e4", "verdict": "fail",
              "checks": {"price_label_ok": False}, "observed": {}}]}, record_seen=False)
        assert not av4["passed"], "no observed value, no correction"
        c.out({"ok": True, "checks": 8})


if __name__ == "__main__":
    main()
