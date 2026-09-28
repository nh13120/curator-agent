"""Run ledger: when did the weekly plan and the daily check last run?

    python3 tools/runs.py record --kind weekly|daily --stop-reason <reason> [--ok true|false] [--summary "..."]
    python3 tools/runs.py stale --kind weekly --days 7      # exit 0 = stale (run it), 1 = fresh
    python3 tools/runs.py show

File: state/last_runs.json. bin/run.sh uses `stale` before a daily check to
catch up on a weekly plan the Mac missed while asleep or off.
"""

from __future__ import annotations

import argparse

import _common as c

FILE = "state/last_runs.json"


def load() -> dict:
    return c.load_json(c.state_path(FILE), default={})


def record(kind: str, stop_reason: str, ok: bool, summary: str) -> dict:
    data = load()
    data[kind] = {"at": c.now().isoformat(timespec="seconds"), "run_id": c.run_id(), "ok": ok,
                  "stop_reason": stop_reason, "summary": summary, "mode": c.MODE}
    c.write_json_atomic(c.state_path(FILE), data)
    return {"ok": True, "recorded": data[kind]}


def stale(kind: str, days: int) -> dict:
    last = load().get(kind)
    if not last:
        return {"ok": True, "stale": True, "reason": f"no {kind} run recorded yet"}
    age = (c.now() - c.parse_dt(last["at"])).total_seconds() / 86400
    return {"ok": True, "stale": age >= days, "days_since": round(age, 1), "last": last}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("record"); p.add_argument("--kind", required=True, choices=["weekly", "daily"])
    p.add_argument("--stop-reason", required=True); p.add_argument("--ok", default="true"); p.add_argument("--summary", default="")
    p = sub.add_parser("stale"); p.add_argument("--kind", required=True, choices=["weekly", "daily"]); p.add_argument("--days", type=int, default=7)
    sub.add_parser("show")
    a = ap.parse_args()
    if a.verb == "record":
        c.out({**record(a.kind, a.stop_reason, a.ok.lower() == "true", a.summary), **c.context_summary()})
    elif a.verb == "stale":
        res = stale(a.kind, a.days)
        c.out(res, exit_code=0 if res["stale"] else 1)
    else:
        c.out({"ok": True, "last_runs": load(), **c.context_summary()})


if __name__ == "__main__":
    main()
