"""Fetch a web page as text, links and forms.

    python3 tools/fetch.py <url> [--max-chars 20000]                  # whole page (default)
    python3 tools/fetch.py <url> --listing --window 2026-10-05..2026-10-11
    python3 tools/fetch.py <url> --event

The default output is the whole page and is what the baseline uses; it does not
change. The two compact modes are for Curator's scouts and verifier and keep
their context small:
  --listing  only the parts of a listing page (or items of a JSON feed) that
             mention a date inside the window, a date range overlapping it, or
             "through <date>"; plus the links named in those parts. If nothing
             matches, `no_dates_in_window` is true and the head of the page is
             returned, so a page with an unusual date format can be refetched whole.
  --event    an event or bio page without its menus and repeated lines, plus
             `facts`: the lines about date, time, price, registration and venue.

Used by the scout and verifier subagents (and the baseline) instead of
WebFetch, because WebFetch cannot reach localhost and caches pages for 15
minutes, which would defeat the verifier's independent re-check.

Safety: in fixture mode only the mock site's origin is allowed. In live and dry
modes any public http(s) host is allowed, but never localhost or private
networks. Page text is returned as data; nothing here interprets it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import re
import urllib.parse
from html.parser import HTMLParser

import _common as c

USER_AGENT = "Curator/0.1 (+personal events assistant; contact via Telegram bot)"


class PageParser(HTMLParser):
    """Collect visible text, links and form fields. Hidden text is kept on
    purpose: the agent must be able to notice injected instructions."""

    SKIP = {"script", "style", "noscript"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.text: list[str] = []
        self.links: list[dict] = []
        self.forms: list[dict] = []
        self._link_text: list[str] | None = None
        self._link_href = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and a.get("href"):
            self._link_href = urllib.parse.urljoin(self.base, a["href"])
            self._link_text = []
        elif tag == "form":
            self.forms.append({"action": urllib.parse.urljoin(self.base, a.get("action", "")),
                               "method": (a.get("method") or "get").lower(), "fields": []})
        elif tag in ("input", "textarea", "select") and self.forms:
            field = {"tag": tag, "name": a.get("name", ""), "type": a.get("type", "text" if tag == "input" else tag),
                     "required": "required" in a, "checked": "checked" in a}
            if a.get("placeholder"):
                field["placeholder"] = a["placeholder"]
            self.forms[-1]["fields"].append(field)
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3", "h4", "tr", "section", "article", "fieldset", "legend", "label"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._link_text is not None:
            label = " ".join("".join(self._link_text).split())
            self.links.append({"text": label, "href": self._link_href})
            self._link_text = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        self.text.append(data)
        if self._link_text is not None:
            self._link_text.append(data)


def host_allowed(url: str) -> tuple[bool, str]:
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https"):
        return False, "only http(s) URLs"
    host = (u.hostname or "").lower()
    if c.MODE == "fixture":
        site = urllib.parse.urlsplit(c.SITE_URL)
        if (host, u.port or 80) != ((site.hostname or "").lower(), site.port or 80):
            return False, f"fixture mode allows only {c.SITE_URL}"
        return True, ""
    if host in ("localhost",) or host.endswith(".local"):
        return False, "local hosts are not allowed outside fixture mode"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, "private network addresses are not allowed"
    except ValueError:
        pass  # a normal hostname
    return True, ""


# ---------------------------------------------------------------- compact modes

MONTH_RE = r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
RE_MD = re.compile(MONTH_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:\s*[-–—]\s*(\d{1,2})\b(?!\s*[:/]))?(?:,?\s+(\d{4}))?", re.I)
RE_DM = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MONTH_RE + r"(?:,?\s+(\d{4}))?", re.I)
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")
RE_US = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?\b")
RE_RANGE = re.compile(r"[–—]|\s-\s|\b(to|through|thru|until|till)\b", re.I)
RE_UNTIL = re.compile(r"\b(through|thru|until|till|on view)\b", re.I)
FACT_RE = re.compile(r"free|admission|ticket|\$\s?\d|price|cost|donation|regist|rsvp|sign up|sold out|waitlist|wait list|capacity|"
                     r"drop[- ]in|open to the public|members|students|location|venue|room|building|address|street|\bave\b|"
                     r"\b\d{1,2}(:\d{2})?\s?(am|pm|a\.m\.|p\.m\.)", re.I)
EVENT_LINK_RE = re.compile(r"event|calendar|program|exhibit|talk|seminar|lecture|screening|film|show|/e/|lu\.ma|luma\.com|meetup\.com", re.I)
FACT_LINK_RE = re.compile(r"regist|rsvp|ticket|eventbrite|lu\.ma|luma\.com|people|person|speaker|bio|artist|faculty|profile|\.ics|calendar", re.I)
MONTHS = {k: i for i, ks in enumerate([("jan",), ("feb",), ("mar",), ("apr",), ("may",), ("jun",), ("jul",), ("aug",),
                                        ("sep",), ("oct",), ("nov",), ("dec",)], 1) for k in ks}


def _mkdate(y, m, d, ref: dt.date):
    try:
        if y:
            y = int(y); y = y + 2000 if y < 100 else y
            return dt.date(y, int(m), int(d))
        options = [dt.date(ref.year + k, int(m), int(d)) for k in (-1, 0, 1)]
        return min(options, key=lambda x: abs((x - ref).days))
    except ValueError:
        return None


def dates_in(text: str, ref: dt.date) -> list:
    out = []
    for mo, d1, d2, y in RE_MD.findall(text):
        m = MONTHS[mo[:3].lower()]
        out += [x for x in (_mkdate(y, m, d1, ref), _mkdate(y, m, d2, ref) if d2 else None) if x]
    for d, mo, y in RE_DM.findall(text):
        x = _mkdate(y, MONTHS[mo[:3].lower()], d, ref); out += [x] if x else []
    for y, m, d in RE_ISO.findall(text):
        x = _mkdate(y, m, d, ref); out += [x] if x else []
    for m, d, y in RE_US.findall(text):
        if 1 <= int(m) <= 12:
            x = _mkdate(y, m, d, ref); out += [x] if x else []
    return out


def touches_window(text: str, start: dt.date, end: dt.date) -> bool:
    ds = dates_in(text, start)
    if any(start <= d <= end for d in ds):
        return True
    if len(ds) >= 2 and RE_RANGE.search(text) and min(ds) <= end and max(ds) >= start:
        return True
    return len(ds) == 1 and bool(RE_UNTIL.search(text)) and ds[0] >= start


def _slim(obj, depth=0):
    """Drop empty values and cut long strings, so a JSON feed item stays readable."""
    if isinstance(obj, dict):
        return {k: _slim(v, depth + 1) for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_slim(v, depth + 1) for v in obj[:20]]
    if isinstance(obj, str) and len(obj) > 300:
        return obj[:300] + "…"
    return obj


def _date_values(obj, key=""):
    """ISO dates found under keys that look like start/end/date fields."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _date_values(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _date_values(v, key)
    elif isinstance(obj, str) and re.search(r"start|end|date|first|last|day|time", key, re.I):
        for y, m, d in RE_ISO.findall(obj):
            x = _mkdate(y, m, d, dt.date.today())
            if x:
                yield x


def _json_items(data):
    """The list of event items in a JSON feed: the largest list of objects."""
    best = []
    def walk(o):
        nonlocal best
        if isinstance(o, list) and o and all(isinstance(x, dict) for x in o) and len(o) > len(best):
            best = o
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return best


def listing_json(raw: str, start: dt.date, end: dt.date, max_chars: int) -> dict:
    try:
        data = json.loads(raw)
    except ValueError:
        return {"text": raw[:max_chars], "truncated": len(raw) > max_chars, "items": [], "no_dates_in_window": True}
    items = _json_items(data)
    kept = []
    for it in items:
        ds = list(_date_values(it))
        if ds and min(ds) <= end and max(ds) >= start:
            kept.append(_slim(it))
    text = json.dumps(kept, ensure_ascii=False)
    return {"items_total": len(items), "items_in_window": len(kept), "items": json.loads(text[:max_chars]) if len(text) <= max_chars else kept[: max(1, len(kept) * max_chars // max(len(text), 1))],
            "truncated": len(text) > max_chars, "no_dates_in_window": not kept}


def listing_html(p: "PageParser", text: str, start: dt.date, end: dt.date, max_chars: int) -> dict:
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if touches_window(line, start, end)]
    spans = []
    for i in hits:
        a, b = max(0, i - 3), min(len(lines), i + 4)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    blocks, used = [], 0
    for a, b in spans:
        block = "\n".join(lines[a:b])
        if used + len(block) > max_chars:
            break
        blocks.append(block); used += len(block)
    joined = "\n".join(blocks)
    named = [l for l in p.links if len(l["text"]) >= 4 and l["text"] in joined]
    seen = {l["href"] for l in named}
    other = [l for l in p.links if l["href"] not in seen and EVENT_LINK_RE.search(l["href"]) and len(l["text"]) >= 4]
    out = {"blocks": blocks, "blocks_truncated": len(blocks) < len(spans), "links": (named + other)[:80 if hits else 30],
           "no_dates_in_window": not hits}
    if not hits:
        out["text_head"] = text[:3000]
    return out


def event_page(p: "PageParser", text: str, max_chars: int) -> dict:
    nav = {l["text"] for l in p.links if l["text"] and len(l["text"].split()) <= 4}
    kept, seen = [], set()
    for line in text.splitlines():
        if line in seen or (line in nav and not FACT_RE.search(line) and not dates_in(line, dt.date.today())):
            continue
        seen.add(line); kept.append(line)
    body = "\n".join(kept)
    facts = [l[:200] for l in kept if FACT_RE.search(l) or dates_in(l, dt.date.today())][:40]
    links = [l for l in p.links if FACT_LINK_RE.search(l["href"]) or FACT_LINK_RE.search(l["text"])][:40]
    return {"text": body[:max_chars], "truncated": len(body) > max_chars, "facts": facts, "links": links}


def fetch(url: str, max_chars: int, mode: str = "full", window: tuple | None = None) -> dict:
    import requests  # lazy: only inside the venv

    ok, why = host_allowed(url)
    if not ok:
        return {"ok": False, "url": url, "error": why, "blocked_by": "fetch_allowlist"}
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        return {"ok": False, "url": url, "error": f"request failed: {e.__class__.__name__}: {e}"}
    ctype = r.headers.get("Content-Type", "")
    head = {"ok": r.ok, "url": url, "final_url": r.url, "status": r.status_code, "content_type": ctype}
    if mode == "listing" and "json" in ctype:
        return {**head, "view": "listing", "window": f"{window[0]}..{window[1]}", **listing_json(r.text, *window, max_chars)}
    if "json" in ctype:
        body = r.text[:max_chars]
        return {"ok": r.ok, "url": url, "final_url": r.url, "status": r.status_code, "content_type": ctype,
                "title": "", "text": body, "truncated": len(r.text) > max_chars, "links": [], "forms": []}
    p = PageParser(r.url)
    p.feed(r.text)
    text = "\n".join(" ".join(line.split()) for line in "".join(p.text).splitlines())
    text = "\n".join(line for line in text.splitlines() if line.strip())
    if mode == "listing":
        return {**head, "view": "listing", "window": f"{window[0]}..{window[1]}", "title": " ".join(p.title.split()),
                **listing_html(p, text, *window, max_chars), "forms": p.forms}
    if mode == "event":
        return {**head, "view": "event", "title": " ".join(p.title.split()), **event_page(p, text, max_chars), "forms": p.forms}
    return {
        "ok": r.ok, "url": url, "final_url": r.url, "status": r.status_code, "content_type": ctype,
        "title": " ".join(p.title.split()), "text": text[:max_chars], "truncated": len(text) > max_chars,
        "links": p.links[:200], "forms": p.forms,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--max-chars", type=int, default=None, help="default 20000; 12000 with --listing, 8000 with --event")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--listing", action="store_true", help="only the parts that mention the --window dates")
    g.add_argument("--event", action="store_true", help="event or bio page without menus, plus `facts`")
    ap.add_argument("--window", help="START..END (YYYY-MM-DD), required with --listing")
    a = ap.parse_args()
    mode = "listing" if a.listing else "event" if a.event else "full"
    window = None
    if mode == "listing":
        try:
            s, e = (a.window or "").split("..")
            window = (dt.date.fromisoformat(s), dt.date.fromisoformat(e))
        except ValueError:
            c.out({"ok": False, "error": "--listing needs --window YYYY-MM-DD..YYYY-MM-DD"}, exit_code=2)
            return
    max_chars = a.max_chars or {"full": 20000, "listing": 12000, "event": 8000}[mode]
    result = fetch(a.url, max_chars, mode, window)
    result["mode"] = c.MODE
    if mode == "full":
        c.out(result, exit_code=0 if result.get("ok") else 1)
    else:  # compact modes: no indentation either
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str))
        raise SystemExit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
