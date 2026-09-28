"""Pending items: everything waiting on an answer from Nicolas.

    python3 tools/pending.py add --kind tier2_field --question "..." [--options "a|b|c"] [--event-id ev_x] [--week W] [--category C] [--ref R]
    python3 tools/pending.py list [--status open|answered|expired|all]
    python3 tools/pending.py mark --id pend_x --field telegram_message_id --value 123
    python3 tools/pending.py answer --id pend_x --answer "2"
    python3 tools/pending.py close --id pend_x [--status answered|expired|withdrawn]
    python3 tools/pending.py selftest

File: state/pending.json  {"items": [{id, kind, created_at, week, category, event_id, ref,
                                      question, options, telegram_message_id, status, answer, answered_at}]}

kinds: tier2_field | tier2_price | out_of_town | tier3_blocker | travel_ambiguous |
       rule_change | cancellation | rating | alert | swap | other
Every escalation to Telegram is recorded here first, so a run can be resumed
and the daily check knows which replies belong to which question.
"""

from __future__ import annotations

import argparse
import uuid

import _common as c

FILE = "state/pending.json"
KINDS = ("tier2_field", "tier2_price", "out_of_town", "tier3_blocker", "travel_ambiguous", "rule_change",
         "cancellation", "rating", "alert", "swap", "other")


def load() -> dict:
    return c.load_json(c.state_path(FILE), default={"items": []})


def save(data: dict) -> None:
    c.write_json_atomic(c.state_path(FILE), data)


def add(kind, question, options, event_id, week, category, ref) -> dict:
    data = load()
    item = {"id": "pend_" + uuid.uuid4().hex[:8], "kind": kind, "created_at": c.now().isoformat(), "run_id": c.run_id(),
            "week": week, "category": category, "event_id": event_id, "ref": ref, "question": question,
            "options": [o.strip() for o in options.split("|")] if options else [],
            "telegram_message_id": None, "status": "open", "answer": None, "answered_at": None}
    data["items"].append(item)
    save(data)
    return {"ok": True, "item": item}


def find(data: dict, id_: str) -> dict | None:
    return next((i for i in data["items"] if i["id"] == id_), None)


def update(id_: str, **fields) -> dict:
    data = load()
    item = find(data, id_)
    if not item:
        return {"ok": False, "error": f"no pending item {id_}"}
    item.update({k: v for k, v in fields.items() if v is not None})
    save(data)
    return {"ok": True, "item": item}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("add"); p.add_argument("--kind", choices=KINDS, required=True); p.add_argument("--question", required=True)
    p.add_argument("--options"); p.add_argument("--event-id"); p.add_argument("--week"); p.add_argument("--category"); p.add_argument("--ref")
    p = sub.add_parser("list"); p.add_argument("--status", default="open")
    p = sub.add_parser("mark"); p.add_argument("--id", required=True); p.add_argument("--field", required=True); p.add_argument("--value", required=True)
    p = sub.add_parser("answer"); p.add_argument("--id", required=True); p.add_argument("--answer", required=True)
    p = sub.add_parser("close"); p.add_argument("--id", required=True); p.add_argument("--status", default="answered", choices=["answered", "expired", "withdrawn"])
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "add":
        res = add(a.kind, a.question, a.options, a.event_id, a.week, a.category, a.ref)
    elif a.verb == "list":
        items = load()["items"]
        if a.status != "all":
            items = [i for i in items if i["status"] == a.status]
        res = {"ok": True, "count": len(items), "items": items}
    elif a.verb == "mark":
        res = update(a.id, **{a.field: a.value})
    elif a.verb == "answer":
        res = update(a.id, answer=a.answer, status="answered", answered_at=c.now().isoformat())
    elif a.verb == "close":
        res = update(a.id, status=a.status)
    else:
        r = add("other", "selftest?", "yes|no", None, None, None, None)
        assert r["ok"] and r["item"]["options"] == ["yes", "no"]
        r2 = update(r["item"]["id"], answer="yes", status="answered")
        assert r2["item"]["status"] == "answered"
        update(r["item"]["id"], status="withdrawn")
        res = {"ok": True, "checks": 2}
    c.out({**res, **c.context_summary()}, exit_code=0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
