"""RSVP form classifier: decides the autonomy tier BEFORE the browser touches a form.

    python3 tools/rsvp.py classify-form --url <registration page url>
    python3 tools/rsvp.py classify-form --snapshot-file <browser_snapshot .yml>   # JS-rendered forms (Eventbrite, Luma)
    python3 tools/rsvp.py classify-form --forms-json <file from fetch.py>   # offline
    python3 tools/rsvp.py selftest

Eventbrite, Luma and most ticketing sites render their forms with JavaScript,
so `--url` (a plain fetch) sees no form there. Take a `browser_snapshot` and
pass its saved .yml file with --snapshot-file: the classifier reads the
textbox / checkbox / combobox / radio lines, keeps their [ref=...] handles,
and returns the same tier and fill plan.

Reads the registration page with tools/fetch.py, looks at every form field
and answers three questions:

  tier 3  Does the form ask for a password, card, CVV, government ID, or an
          account? -> stop, never fill, report to Nicolas.
  tier 2  Is there a required field the profile cannot fill (free-text
          questions like "Why do you want to attend?", shift selection)?
          -> ask Nicolas first.
  tier 1  Every required field maps to a profile value -> book automatically.

It also returns the fill plan: which field gets which profile value, and which
opt-in checkboxes must be left (or made) unchecked. The plan never contains
invented values; a field with no source is listed under `unfillable`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import _common as c

SENSITIVE = re.compile(
    r"(password|passcode|card|cvv|cvc|expir|ssn|social.?security|passport|licen[cs]e|national.?id|tax.?id|"
    r"routing|account.?number|iban|create.?account|sign.?up.?for.?an.?account)", re.I)
OPT_IN = re.compile(r"(newsletter|subscribe|mailing|marketing|sponsor|share.?my|updat|promotion|partner|keep me (informed|posted))", re.I)
COMMITMENT = re.compile(r"(volunteer|shift|donat|pledge|membership|deposit)", re.I)
CONSENT = re.compile(r"(agree to (the )?(event )?terms|terms (of|and) (service|use|conditions)|code of conduct|privacy policy|photo|photograph|recording)", re.I)

# Field name/placeholder -> profile key. Order matters: first match wins.
PROFILE_MAP = [
    (re.compile(r"first.?name|given.?name|name.?\[?first|fname", re.I), "first_name"),
    (re.compile(r"last.?name|family.?name|surname|name.?\[?last|lname", re.I), "last_name"),
    (re.compile(r"^(full.?)?name$|^your.?name|first.?and.?last|attendee.?name", re.I), "name"),
    (re.compile(r"e-?mail", re.I), "email"),
    (re.compile(r"phone|mobile|tel", re.I), "phone"),
    (re.compile(r"affiliat|organi[sz]ation|company|institution|school|employer", re.I), "affiliation"),
    (re.compile(r"program|degree|course.?of.?study", re.I), "program"),
    (re.compile(r"student|status|role|title", re.I), "student_status"),
    (re.compile(r"address|street", re.I), "home_address"),
]


SNAPSHOT_LINE = re.compile(r'^\s*-\s+(textbox|checkbox|combobox|radio|spinbutton|listbox|switch)\s+"([^"]*)"(.*)$')


def forms_from_snapshot(text: str) -> list[dict]:
    """Turn a Playwright accessibility snapshot into the same field list
    fetch.py produces, so classify() works on JS-rendered pages. Required is
    inferred from a trailing * or "(required)" in the accessible name; the
    [ref=…] handle is kept so the agent can fill exactly that element."""
    fields = []
    for line in text.splitlines():
        m = SNAPSHOT_LINE.match(line)
        if not m:
            continue
        role, name, rest = m.groups()
        ref = re.search(r"\[ref=([^\]]+)\]", rest)
        ftype = {"textbox": "text", "checkbox": "checkbox", "combobox": "select", "radio": "radio",
                 "spinbutton": "number", "listbox": "select", "switch": "checkbox"}[role]
        if re.search(r"e-?mail", name, re.I) and ftype == "text":
            ftype = "email"
        fields.append({"tag": role, "name": name.strip(), "type": ftype,
                       "required": bool(re.search(r"\*\s*$|\(required\)|required", name, re.I) or re.search(r"\brequired\b", rest, re.I)),
                       "checked": "[checked]" in rest, "ref": ref.group(1) if ref else None})
    return [{"action": "(browser page)", "method": "post", "fields": fields}] if fields else []


def classify(forms: list[dict], profile: dict) -> dict:
    if not forms:
        return {"ok": True, "tier": 0, "reason": "no form on the page (drop-in event or registration elsewhere)",
                "fill": [], "leave_unchecked": [], "unfillable": [], "blockers": []}
    # Take the form that posts (registration), else the first one.
    form = next((f for f in forms if f.get("method") == "post"), forms[0])
    fill, unchecked, unfillable, blockers, commitments = [], [], [], [], []
    if not [f for f in form.get("fields", []) if f.get("type") not in ("hidden", "submit", "button")]:
        return {"ok": True, "tier": 0, "no_fields": True,
                "reason": "the form has no fields yet: on a JS site the step has not rendered; snapshot again after it loads",
                "fill": [], "leave_unchecked": [], "unfillable": [], "blockers": []}
    for f in form.get("fields", []):
        name = f.get("name", "")
        # "Name *", "Email address (required)" -> "Name", "Email address" for matching
        label = re.sub(r"\s*(\*|\(required\)|required)\s*$", "", f"{name} {f.get('placeholder', '')}".strip(), flags=re.I)
        ftype = f.get("type", "text")
        if ftype in ("hidden", "submit", "button"):
            continue
        if SENSITIVE.search(label) or ftype == "password":
            blockers.append({"field": name, "why": "tier 3: sensitive field"})
            continue
        if ftype == "checkbox":
            if OPT_IN.search(label):
                unchecked.append({"field": name, "currently_checked": bool(f.get("checked")), "ref": f.get("ref")})
            elif CONSENT.search(label):
                # Routine registration terms are part of attending, not a commitment beyond it.
                fill.append({"field": name, "profile_key": "(consent to event terms)", "value": "check", "ref": f.get("ref")})
            elif f.get("required"):
                unfillable.append({"field": name, "why": "required checkbox with unknown meaning", "ref": f.get("ref")})
            continue
        if COMMITMENT.search(label):
            commitments.append({"field": name, "why": "looks like a commitment beyond attending"})
        key = next((k for pat, k in PROFILE_MAP if pat.search(label)), None)
        value = profile.get(key) if key else None
        if value:
            fill.append({"field": name, "profile_key": key, "value": value, "ref": f.get("ref")})
        elif f.get("required"):
            saved = (profile.get("saved_answers") or {}).get(c.norm(label))
            if saved:
                fill.append({"field": name, "profile_key": f"saved_answers[{c.norm(label)}]", "value": saved, "ref": f.get("ref")})
            else:
                unfillable.append({"field": name, "type": ftype, "why": "required, not in profile", "ref": f.get("ref")})
        # optional fields without a value are simply left blank
    if blockers:
        tier, reason = 3, "form asks for a password, payment or ID field; never fill it"
    elif unfillable or commitments:
        tier, reason = 2, "a required field is not in the profile or the form asks for a commitment; ask Nicolas"
    else:
        tier, reason = 1, "every required field can be filled from the profile"
    return {"ok": True, "tier": tier, "reason": reason, "action": form.get("action"), "fill": fill,
            "leave_unchecked": unchecked, "unfillable": unfillable + commitments, "blockers": blockers}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("classify-form")
    p.add_argument("--url")
    p.add_argument("--forms-json", help="path to a fetch.py output file (offline)")
    p.add_argument("--snapshot-file", help="a browser_snapshot .yml file (JS-rendered forms)")
    sub.add_parser("selftest")
    a = ap.parse_args()

    profile = c.load_yaml(c.profile_path(), default={}) or {}
    if a.verb == "selftest":
        std = [{"method": "post", "action": "/register/x", "fields": [
            {"name": "name", "type": "text", "required": True}, {"name": "email", "type": "email", "required": True},
            {"name": "affiliation", "type": "text", "required": True}, {"name": "phone", "type": "text", "required": False},
            {"name": "newsletter", "type": "checkbox", "checked": True}, {"name": "sponsors", "type": "checkbox", "checked": True}]}]
        r1 = classify(std, {"name": "T", "email": "t@x", "affiliation": "MIT"})
        assert r1["tier"] == 1 and len(r1["leave_unchecked"]) == 2, r1
        why = [dict(std[0], fields=std[0]["fields"] + [{"name": "why_attend", "type": "textarea", "required": True}])]
        assert classify(why, {"name": "T", "email": "t@x", "affiliation": "MIT"})["tier"] == 2
        card = [dict(std[0], fields=std[0]["fields"] + [{"name": "card_number", "type": "text", "required": True}])]
        assert classify(card, {"name": "T", "email": "t@x", "affiliation": "MIT"})["tier"] == 3
        assert classify([], {})["tier"] == 0
        snap = """- heading "Register" [level=1]
- textbox "First Name*" [ref=e10]
- textbox "Last Name*" [ref=e11]
- textbox "Email Address*" [ref=e12]
- checkbox "Keep me updated on more events and news from this event organizer." [checked] [ref=e20]
- button "Register" [ref=e30]"""
        r5 = classify(forms_from_snapshot(snap), {"first_name": "T", "last_name": "S", "email": "t@x"})
        assert r5["tier"] == 1 and [f["ref"] for f in r5["fill"]] == ["e10", "e11", "e12"] and r5["leave_unchecked"][0]["ref"] == "e20", r5
        card = forms_from_snapshot('- textbox "Card number*" [ref=e1]')
        assert classify(card, {})["tier"] == 3
        luma = forms_from_snapshot("""- textbox "Name *" [ref=e1]
- textbox "Email *" [ref=e2]
- textbox "What company or org are you with? *" [ref=e3]
- checkbox "By registering, I agree to the event terms." [ref=e4] required""")
        r7 = classify(luma, {"name": "T S", "email": "t@x", "affiliation": "MIT"})
        assert r7["tier"] == 1 and [f["ref"] for f in r7["fill"]] == ["e1", "e2", "e3", "e4"], r7
        assert classify([{"method": "post", "fields": []}], {})["tier"] == 0
        c.out({"ok": True, "checks": 8})
        return
    if a.snapshot_file:
        forms = forms_from_snapshot(Path(a.snapshot_file).read_text())
    elif a.forms_json:
        forms = c.load_json(a.forms_json)["forms"]
    elif a.url:
        from fetch import fetch

        page = fetch(a.url, 20000)
        if not page.get("ok"):
            c.out({**page, **c.context_summary()}, exit_code=1)
        forms = page["forms"]
    else:
        c.fail("classify-form needs --url, --snapshot-file or --forms-json")
    if not profile:
        c.fail(f"profile not found at {c.profile_path()}; copy config/profile.example.yaml and fill it in")
    res = classify(forms, profile)
    res["profile_source"] = str(c.profile_path())
    c.out({**res, **c.context_summary()}, exit_code=0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
