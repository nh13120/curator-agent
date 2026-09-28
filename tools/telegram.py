"""Telegram bot channel: the only way Curator talks to Nicolas.

    python3 tools/telegram.py send --text "..." [--kind booked|summary|question|rating|alert|status] [--ref <id>]
    python3 tools/telegram.py get_updates            # unread replies from Nicolas (non-destructive)
    python3 tools/telegram.py ack --through <update_id>   # mark replies processed
    python3 tools/telegram.py whoami                 # setup helper: shows chat ids that messaged the bot
    python3 tools/telegram.py selftest

Modes
  live     sends through api.telegram.org and reads real replies.
  dry      sends for real too, prefixed "[DRY RUN]" (the brief asks for this), reads real replies.
  fixture  never touches the network: outgoing messages go to state/telegram_outbox.jsonl,
           replies come from fixtures/cases/<case>/telegram_inbox.json.

Every message sent (in any mode) is also appended to state/telegram_outbox.jsonl
so the run has a record of what Nicolas was told. Secrets come from .env
(CURATOR_TELEGRAM_BOT_TOKEN, CURATOR_TELEGRAM_CHAT_ID) and are never printed.

There is no always-on server: replies are read at the start of each run.
CURATOR_FAULT=telegram makes the first network call of a run fail once, for
the failure-recovery tests.
"""

from __future__ import annotations

import argparse
import os

import _common as c

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram's limit is 4096 characters


def load_env() -> None:
    from dotenv import load_dotenv  # inside the venv

    load_dotenv(c.PROJECT_ROOT / ".env", override=False)


def creds() -> tuple[str, str]:
    load_env()
    token = os.environ.get("CURATOR_TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("CURATOR_TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise RuntimeError("CURATOR_TELEGRAM_BOT_TOKEN is not set in .env")
    return token, chat


def maybe_fault() -> None:
    """Fail once per run when CURATOR_FAULT=telegram, to exercise the retry path."""
    if c.FAULT != "telegram":
        return
    marker = c.state_path("state/.fault_telegram_fired")
    if not marker.exists():
        marker.write_text("1")
        raise RuntimeError("simulated network error (CURATOR_FAULT=telegram)")


def api(method: str, **params) -> dict:
    import requests

    token, _ = creds()
    maybe_fault()
    r = requests.post(API.format(token=token, method=method), json=params, timeout=20)
    data = r.json()
    if not data.get("ok"):
        # Telegram error descriptions never contain the token; safe to surface.
        raise RuntimeError(f"telegram {method} failed: {data.get('description', r.status_code)}")
    return data["result"]


def record_outgoing(text: str, kind: str, ref: str | None, delivered: str, message_id=None) -> dict:
    row = {"ts": c.now().isoformat(), "run_id": c.run_id(), "mode": c.MODE, "kind": kind, "ref": ref,
           "text": text, "delivered": delivered, "message_id": message_id}
    c.append_jsonl(c.state_path("state/telegram_outbox.jsonl"), row)
    return row


def send(text: str, kind: str, ref: str | None) -> dict:
    text = text.strip()
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 20] + "\n… (truncated)"
    try:
        maybe_fault()  # failure tests: fails once per run in every mode
    except RuntimeError as e:
        record_outgoing(text, kind, ref, delivered="failed")
        return {"ok": False, "error": str(e), "retryable": True}
    if c.MODE == "fixture":
        c.log_write_attempt("telegram.send", {"kind": kind, "chars": len(text)}, blocked=False, simulated=True)
        row = record_outgoing(text, kind, ref, delivered="simulated")
        return {"ok": True, "simulated": True, "message": row}
    if c.MODE == "dry":
        text = "[DRY RUN] " + text
    c.log_write_attempt("telegram.send", {"kind": kind, "chars": len(text), "dry_prefixed": c.MODE == "dry"}, blocked=False)
    try:
        _, chat = creds()
        if not chat:
            raise RuntimeError("CURATOR_TELEGRAM_CHAT_ID is not set in .env (run `whoami` after messaging the bot)")
        result = api("sendMessage", chat_id=chat, text=text, disable_web_page_preview=True)
    except Exception as e:
        record_outgoing(text, kind, ref, delivered="failed")
        return {"ok": False, "error": str(e), "retryable": True}
    row = record_outgoing(text, kind, ref, delivered="sent", message_id=result.get("message_id"))
    return {"ok": True, "simulated": False, "message": row}


def normalize(update: dict) -> dict | None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    return {"update_id": update["update_id"], "message_id": msg.get("message_id"), "date": msg.get("date"),
            "chat_id": str((msg.get("chat") or {}).get("id", "")), "text": msg.get("text", ""),
            "reply_to_message_id": (msg.get("reply_to_message") or {}).get("message_id")}


def offset_path():
    return c.state_path("state/telegram_offset.json")


def live_offset() -> int:
    return (c.load_json(c.PROJECT_ROOT / "state" / "telegram_offset.json", default={"through": 0}) or {}).get("through", 0)


def get_updates(all_chats: bool = False) -> dict:
    consumed = c.load_json(offset_path(), default={"through": 0})["through"]
    # Asking Telegram for updates after offset N deletes everything up to N on
    # the server. A dry run must never do that beyond what the LIVE run has
    # already handled, or the next live run would miss Nicolas's replies. So the
    # server is always asked from the live offset; the dry offset only hides
    # messages this dry state has already answered.
    server_from = live_offset() if c.MODE == "dry" else consumed
    if c.MODE == "fixture":
        inbox = c.load_json(c.fixture_path("telegram_inbox.json"), default={"updates": []})["updates"]
        rows = [normalize(u) for u in inbox]
        rows = [r for r in rows if r and r["update_id"] > consumed]
        return {"ok": True, "source": "fixture", "messages": rows, "consumed_through": consumed}
    try:
        _, chat = creds()
        updates = api("getUpdates", offset=server_from + 1, timeout=0)
    except Exception as e:
        return {"ok": False, "error": str(e), "retryable": True, "messages": []}
    rows = [normalize(u) for u in updates]
    rows = [r for r in rows if r and (all_chats or not chat or r["chat_id"] == chat) and r["update_id"] > consumed]
    return {"ok": True, "source": "telegram", "messages": rows, "consumed_through": consumed, "server_offset_from": server_from,
            "ignored_other_chats": sum(1 for u in updates if normalize(u) and chat and normalize(u)["chat_id"] != chat)}


def ack(through: int) -> dict:
    c.write_json_atomic(offset_path(), {"through": through, "at": c.now().isoformat()})
    return {"ok": True, "consumed_through": through}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("send"); p.add_argument("--text", required=True)
    p.add_argument("--kind", default="message", choices=["booked", "summary", "question", "rating", "alert", "status", "message"])
    p.add_argument("--ref", default=None, help="what the message is about (event id, pending id)")
    sub.add_parser("get_updates")
    p = sub.add_parser("ack"); p.add_argument("--through", type=int, required=True)
    sub.add_parser("whoami")
    sub.add_parser("selftest")
    a = ap.parse_args()

    if a.verb == "send":
        res = send(a.text, a.kind, a.ref)
    elif a.verb == "get_updates":
        res = get_updates()
    elif a.verb == "ack":
        res = ack(a.through)
    elif a.verb == "whoami":
        res = get_updates(all_chats=True)
        if res.get("ok"):
            res = {"ok": True, "chats_seen": sorted({m["chat_id"] for m in res["messages"]}),
                   "hint": "put your chat id in .env as CURATOR_TELEGRAM_CHAT_ID"}
    else:
        assert c.MODE == "fixture", "selftest runs in fixture mode: CURATOR_MODE=fixture CURATOR_CASE=<case>"
        r = send("selftest hello", "message", None)
        assert r["ok"] and r["simulated"]
        u = get_updates()
        assert u["ok"] and u["source"] == "fixture"
        res = {"ok": True, "checks": 2, "outbox": str(c.state_path("state/telegram_outbox.jsonl"))}
    c.out({**res, **c.context_summary()}, exit_code=0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
