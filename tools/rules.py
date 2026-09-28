"""Rules: read and change config/rules.yaml with a logged diff.

    python3 tools/rules.py show [--format text|json]
    python3 tools/rules.py get --path categories.0.per_week
    python3 tools/rules.py set --path max_travel_min --value 30 --request "max 30 min travel" [--source telegram]
    python3 tools/rules.py exclude --kind topics|speakers|venues --value "crypto" --request "no more crypto talks"
    python3 tools/rules.py add-category --id film --label "Film" --per-week 1 --every-n-weeks 2 --request "..."
    python3 tools/rules.py remove-category --id film --request "..."
    python3 tools/rules.py history
    python3 tools/rules.py selftest

Interpreting a free-text request ("no more crypto talks") is the agent's job;
this tool applies the concrete change, validates the file still loads, and
appends {request, changes, diff} to memory/rules_history.jsonl. If the agent
cannot map a request to one of these commands unambiguously, it must ask
Nicolas instead of guessing.

--value is parsed as YAML, so `30` is a number, `true` a boolean, `[a, b]` a list.
"""

from __future__ import annotations

import argparse
import difflib
import io
import json

import _common as c

RULES = c.PROJECT_ROOT / "config" / "rules.yaml"
HISTORY = "memory/rules_history.jsonl"
PROTECTED = ("free_only", "auto_book_price_labels", "excluded_price_labels")  # guardrails the brief calls non-negotiable


def _yaml():
    """Round-trip YAML: keeps comments, order and the [a, b] list style, so a
    one-value change produces a one-line diff and the file stays readable."""
    from ruamel.yaml import YAML

    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 120
    y.indent(mapping=2, sequence=4, offset=2)  # matches the hand-written "  - id:" style
    return y


def load_text() -> str:
    return RULES.read_text()


def load():
    return _yaml().load(load_text()) or {}


def dump(data) -> str:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


def resolve(data, path: str, create: bool = False):
    """Walk a dotted path; list indexes are integers. Returns (parent, key)."""
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        key = int(part) if isinstance(node, list) else part
        if isinstance(node, dict) and key not in node:
            if not create:
                raise KeyError(path)
            node[key] = {}
        node = node[key]
    last = parts[-1]
    return node, (int(last) if isinstance(node, list) else last)


def commit(before_text: str, data: dict, request: str, source: str, changes: list[dict]) -> dict:
    """Write the new rules, verify they load, log the diff."""
    import yaml

    after_text = dump(data)
    yaml.safe_load(after_text)  # plain loader: raises if we produced something invalid
    diff = "".join(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True),
                                        "rules.yaml (before)", "rules.yaml (after)"))
    c.append_jsonl(c.state_path(HISTORY), {"at": c.now().isoformat(), "source": source, "request_text": request,
                                           "changes": changes, "diff": diff, "applied": True, "run_id": c.run_id()})
    RULES.write_text(after_text)
    return {"ok": True, "changes": changes, "diff": diff}


def set_value(path: str, value, request: str, source: str) -> dict:
    if path.split(".")[0] in PROTECTED:
        return {"ok": False, "error": f"{path} is a non-negotiable guardrail and cannot be changed through rules.py"}
    before = load_text()
    data = load()
    parent, key = resolve(data, path, create=True)
    old = parent[key] if (isinstance(parent, dict) and key in parent) or (isinstance(parent, list) and key < len(parent)) else None
    parent[key] = value
    plain = lambda v: json.loads(json.dumps(v, default=str)) if not isinstance(v, (int, float, str, bool, type(None))) else v
    return commit(before, data, request, source, [{"path": path, "old": plain(old), "new": plain(value)}])


def exclude(kind: str, value: str, request: str, source: str) -> dict:
    before = load_text()
    data = load()
    lst = data.setdefault("exclusions", {}).setdefault(kind, [])
    if value in lst:
        return {"ok": True, "changes": [], "diff": "", "note": f"{value!r} already excluded"}
    old = list(lst)
    lst.append(value)
    return commit(before, data, request, source, [{"path": f"exclusions.{kind}", "old": old, "new": list(lst)}])


def add_category(id_, label, per_week, every_n_weeks, description, request, source) -> dict:
    before = load_text()
    data = load()
    if any(cat["id"] == id_ for cat in data["categories"]):
        return {"ok": False, "error": f"category {id_} exists; use set --path categories.<i>.per_week"}
    cat = {"id": id_, "label": label, "per_week": per_week, "every_n_weeks": every_n_weeks, "description": description or ""}
    data["categories"].append(cat)
    return commit(before, data, request, source, [{"path": "categories", "old": None, "new": dict(cat)}])


def remove_category(id_, request, source) -> dict:
    before = load_text()
    data = load()
    keep = [cat for cat in data["categories"] if cat["id"] != id_]
    if len(keep) == len(data["categories"]):
        return {"ok": False, "error": f"no category {id_}"}
    data["categories"] = keep
    return commit(before, data, request, source, [{"path": "categories", "old": id_, "new": None}])


def show_text(data: dict) -> str:
    cats = ", ".join(f"{cat['label']} ×{cat['per_week']}" + (f" every {cat['every_n_weeks']} weeks" if cat.get("every_n_weeks", 1) > 1 else "")
                     for cat in data["categories"])
    ex = data.get("exclusions", {})
    ex_txt = "; ".join(f"{k}: {', '.join(v)}" for k, v in ex.items() if v) or "none"
    sw = data.get("swaps", {})
    return "\n".join([
        f"Curator rules (v{data.get('version')}), home {data.get('home_city')}:",
        f"• Weekly: {cats}",
        f"• Free only; auto-book {', '.join(data.get('auto_book_price_labels', []))}; ask first for {', '.join(data.get('ask_first_price_labels', []))}",
        f"• In person only: {data.get('in_person_only')}; travel ≤ {data.get('max_travel_min')} min; buffer {data.get('buffer_min')} min",
        f"• No events after {data.get('evening_cutoff')} the day before an unsubmitted deadline",
        f"• Skip a category if the calendar already has a one-off event of it: {data.get('skip_category_if_calendar_has_one_off')}",
        f"• Swaps: {'allowed' if sw.get('allowed') else 'off'} (higher speaker tier, > {sw.get('min_days_ahead')} days ahead); waitlists: {'yes' if data.get('waitlists') else 'no'}",
        f"• Away: quota optional, speaker tier ≥ {data.get('away', {}).get('min_speaker_tier')}, ask first",
        f"• Exclusions: {ex_txt}",
    ])


def main() -> None:
    import yaml

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("show"); p.add_argument("--format", choices=["text", "json"], default="text")
    p = sub.add_parser("get"); p.add_argument("--path", required=True)
    p = sub.add_parser("set"); p.add_argument("--path", required=True); p.add_argument("--value", required=True)
    p.add_argument("--request", required=True); p.add_argument("--source", default="manual")
    p = sub.add_parser("exclude"); p.add_argument("--kind", choices=["topics", "speakers", "venues"], required=True)
    p.add_argument("--value", required=True); p.add_argument("--request", required=True); p.add_argument("--source", default="manual")
    p = sub.add_parser("add-category"); p.add_argument("--id", required=True); p.add_argument("--label", required=True)
    p.add_argument("--per-week", type=int, default=1); p.add_argument("--every-n-weeks", type=int, default=1)
    p.add_argument("--description", default=""); p.add_argument("--request", required=True); p.add_argument("--source", default="manual")
    p = sub.add_parser("remove-category"); p.add_argument("--id", required=True); p.add_argument("--request", required=True); p.add_argument("--source", default="manual")
    sub.add_parser("history")
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "show":
        data = load()
        res = {"ok": True, "text": show_text(data)} if a.format == "text" else {"ok": True, "rules": data}
    elif a.verb == "get":
        parent, key = resolve(load(), a.path)
        res = {"ok": True, "path": a.path, "value": parent[key]}
    elif a.verb == "set":
        res = set_value(a.path, yaml.safe_load(a.value), a.request, a.source)
    elif a.verb == "exclude":
        res = exclude(a.kind, a.value, a.request, a.source)
    elif a.verb == "add-category":
        res = add_category(a.id, a.label, a.per_week, a.every_n_weeks, a.description, a.request, a.source)
    elif a.verb == "remove-category":
        res = remove_category(a.id, a.request, a.source)
    elif a.verb == "history":
        res = {"ok": True, "history": c.read_jsonl(c.state_path(HISTORY))}
    else:
        data = load()
        assert resolve(data, "categories.0.per_week")[0]["per_week"] == data["categories"][0]["per_week"]
        assert set_value("free_only", False, "x", "manual")["ok"] is False  # guardrail protected
        assert "Weekly" in show_text(data)
        res = {"ok": True, "checks": 3}
    c.out({**res, **c.context_summary()}, exit_code=0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
