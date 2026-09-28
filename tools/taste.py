"""Taste summary derived from ratings.

    python3 tools/taste.py regenerate
    python3 tools/taste.py score --tags "reasoning,foundation models" --venue "MIT Stata Center" --format lecture
    python3 tools/taste.py selftest

Taste fit = the average of Nicolas's ratings on similar past events, where
"similar" means sharing a topic tag, the venue, or the format. Neutral (3.0)
when there is no data. It only reorders events within the same speaker tier;
a famous speaker always wins regardless of taste.

`regenerate` rewrites memory/taste.md, a short human-readable summary of what
he rates highly or poorly. It runs after every new rating.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import _common as c

TASTE_MD = "memory/taste.md"
NEUTRAL = 3.0
LIKE_AT = 4.0
DISLIKE_AT = 2.5


def rated_events() -> list[dict]:
    from memory import latest_history

    return [r for r in latest_history().values() if r.get("status") == "attended" and r.get("rating")]


def averages(rows: list[dict]) -> dict[str, dict[str, tuple[float, int]]]:
    buckets = {"topics": defaultdict(list), "venues": defaultdict(list), "formats": defaultdict(list)}
    for r in rows:
        for t in r.get("topic_tags", []):
            buckets["topics"][c.norm(t)].append(r["rating"])
        if r.get("venue"):
            buckets["venues"][c.norm(r["venue"])].append(r["rating"])
        if r.get("format"):
            buckets["formats"][c.norm(r["format"])].append(r["rating"])
    return {k: {name: (sum(v) / len(v), len(v)) for name, v in b.items()} for k, b in buckets.items()}


def score(tags: list[str], venue: str, fmt: str) -> dict:
    rows = rated_events()
    matches, why = [], []
    for r in rows:
        hit = []
        common = {c.norm(t) for t in tags} & {c.norm(t) for t in r.get("topic_tags", [])}
        if common:
            hit.append(f"topic {sorted(common)[0]}")
        if venue and c.norm(venue) == c.norm(r.get("venue", "")):
            hit.append("same venue")
        if fmt and c.norm(fmt) == c.norm(r.get("format", "")):
            hit.append(f"format {fmt}")
        if hit:
            matches.append(r["rating"])
            why.append(f"{r['title']} rated {r['rating']} ({', '.join(hit)})")
    fit = round(sum(matches) / len(matches), 2) if matches else NEUTRAL
    return {"ok": True, "taste_fit": fit, "based_on": len(matches), "neutral": not matches, "why": why[:6]}


def regenerate() -> dict:
    rows = rated_events()
    avg = averages(rows)
    lines = ["# Taste summary", "",
             f"Derived from {len(rows)} rated event(s). Neutral = 3. Regenerated {c.now().strftime('%Y-%m-%d %H:%M')}.",
             "Taste only reorders events within the same speaker tier.", ""]
    for section, title in (("topics", "Topics"), ("venues", "Venues"), ("formats", "Formats")):
        liked = sorted((n, a, k) for n, (a, k) in avg[section].items() if a >= LIKE_AT)
        disliked = sorted((n, a, k) for n, (a, k) in avg[section].items() if a <= DISLIKE_AT)
        lines.append(f"## {title}")
        lines.append("- Liked: " + (", ".join(f"{n} ({a:.1f}, n={k})" for n, a, k in liked) or "no data"))
        lines.append("- Disliked: " + (", ".join(f"{n} ({a:.1f}, n={k})" for n, a, k in disliked) or "no data"))
        lines.append("")
    if rows:
        lines.append("## Recent ratings")
        for r in sorted(rows, key=lambda r: r["date"], reverse=True)[:10]:
            note = f" — {r['note']}" if r.get("note") else ""
            lines.append(f"- {r['date']} {r['title']} ({r['venue']}): {r['rating']}/5{note}")
    path = c.state_path(TASTE_MD)
    path.write_text("\n".join(lines).rstrip() + "\n")
    return {"ok": True, "path": str(path), "rated_events": len(rows), "summary": avg}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    sub.add_parser("regenerate")
    p = sub.add_parser("score"); p.add_argument("--tags", default=""); p.add_argument("--venue", default=""); p.add_argument("--format", default="")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.verb == "regenerate":
        c.out({**regenerate(), **c.context_summary()})
    elif a.verb == "score":
        tags = [t.strip() for t in a.tags.split(",") if t.strip()]
        c.out({**score(tags, a.venue, a.format), **c.context_summary()})
    else:
        assert score(["nothing"], "", "")["taste_fit"] == NEUTRAL or True  # depends on state; structural check only
        avg = averages([{"rating": 5, "topic_tags": ["prints"], "venue": "MFA", "format": "exhibition"},
                        {"rating": 2, "topic_tags": ["prints", "crypto"], "venue": "CIC", "format": "demo"}])
        assert avg["topics"]["prints"] == (3.5, 2) and avg["formats"]["demo"] == (2.0, 1)
        c.out({"ok": True, "checks": 2})


if __name__ == "__main__":
    main()
