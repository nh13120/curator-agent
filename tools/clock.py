"""Planning-horizon calculator.

    python3 tools/clock.py context      # what week(s) to plan, today, mode
    python3 tools/clock.py selftest

Rule from the brief: the weekly run plans the Monday-Sunday week that starts on
the first Monday at least 4 weeks after the run date, and re-scans the weeks in
between. Example: a run on Saturday 2026-09-26 targets Monday 2026-10-26.

In fixture mode a case can narrow the horizon with `plan_weeks` in case.json so
evaluation runs stay bounded and comparable.
"""

import argparse
import datetime as dt
import os

import _common as c


def target_week(run_date: dt.date) -> dt.date:
    earliest = run_date + dt.timedelta(days=28)
    # Walk forward to the first Monday on or after `earliest`.
    return earliest + dt.timedelta(days=(7 - earliest.weekday()) % 7)


def horizon(run_date: dt.date) -> list[dt.date]:
    """Mondays from next week up to and including the target week."""
    weeks = []
    w = c.week_start(run_date) + dt.timedelta(days=7)
    end = target_week(run_date)
    while w <= end:
        weeks.append(w)
        w += dt.timedelta(days=7)
    return weeks


def context() -> dict:
    today = c.now()
    tw = target_week(today.date())
    weeks = horizon(today.date())
    restrict = None
    if c.MODE == "fixture":
        case = c.load_json(c.fixture_path("case.json"), default={})
        restrict = case.get("plan_weeks")
    if restrict:
        weeks = [dt.date.fromisoformat(w) for w in restrict]
    source_ids = [s.strip() for s in os.environ.get("CURATOR_SOURCE_IDS", "").split(",") if s.strip()]
    return {
        "ok": True,
        "source_ids_override": source_ids or None,
        "now": today.isoformat(),
        "today": today.date().isoformat(),
        "weekday": today.strftime("%A"),
        "timezone": "America/New_York",
        "target_week": {"start": tw.isoformat(), "end": (tw + dt.timedelta(days=6)).isoformat()},
        "plan_weeks": [{"start": w.isoformat(), "end": (w + dt.timedelta(days=6)).isoformat()} for w in weeks],
        **c.context_summary(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verb", choices=["context", "selftest"])
    a = ap.parse_args()
    if a.verb == "context":
        c.out(context())
    else:
        assert target_week(dt.date(2026, 9, 26)) == dt.date(2026, 10, 26)   # brief's example
        assert target_week(dt.date(2026, 9, 28)) == dt.date(2026, 10, 26)   # Monday run, 4 weeks exactly
        assert target_week(dt.date(2026, 9, 29)) == dt.date(2026, 11, 2)    # Tuesday run, rolls forward
        assert horizon(dt.date(2026, 9, 26))[0] == dt.date(2026, 9, 28)
        assert horizon(dt.date(2026, 9, 26))[-1] == dt.date(2026, 10, 26)
        c.out({"ok": True, "checks": 5})


if __name__ == "__main__":
    main()
