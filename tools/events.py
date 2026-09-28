"""Event identity helpers as a CLI.

    python3 tools/events.py id --title "..." --date 2026-10-29 --venue "..."
    python3 tools/events.py talk-key --title "..." --speaker "A" --speaker "B"
    python3 tools/events.py selftest

The same functions live in tools/_common.py and are used by the mock site and
the eval checker, so every part of the system agrees on what "the same event"
means.
"""

import argparse

import _common as c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("id", help="stable event id")
    p.add_argument("--title", required=True)
    p.add_argument("--date", required=True, help="YYYY-MM-DD (opening day for exhibitions)")
    p.add_argument("--venue", required=True)

    p = sub.add_parser("talk-key", help="same-speaker-same-talk key")
    p.add_argument("--title", required=True)
    p.add_argument("--speaker", action="append", default=[])

    sub.add_parser("selftest")

    a = ap.parse_args()
    if a.verb == "id":
        c.out({"ok": True, "event_id": c.event_id(a.title, a.date, a.venue)})
    elif a.verb == "talk-key":
        c.out({"ok": True, "talk_key": c.talk_key(a.title, a.speaker)})
    elif a.verb == "selftest":
        # Same event described slightly differently must produce the same id.
        a1 = c.event_id("The Future of AI: A Talk", "2026-10-29", "MIT Stata Center")
        a2 = c.event_id("future of ai  a talk", "2026-10-29T18:00:00-04:00", "mit stata center")
        b = c.event_id("The Future of AI: A Talk", "2026-10-30", "MIT Stata Center")
        assert a1 == a2, "normalization failed"
        assert a1 != b, "date must change the id"
        assert c.norm("Café Ölé!") == "cafe ole"
        c.out({"ok": True, "checks": 3, "example_id": a1})


if __name__ == "__main__":
    main()
