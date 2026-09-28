"""SubagentStop hook: save a scout's or verifier's JSON reply for the main agent.

The main agent used to copy each reply into `candidates.py save` by hand, which
cost minutes of model output per run and risked transcription slips. This hook
takes the subagent's final message (`last_assistant_message`), checks it is one
JSON object, and writes it where the pipeline expects it:

  scout     -> state/candidates/<category>.raw.json       (candidates from every
               city scouted for that category in this run are merged; the
               per-city replies are kept in <category>.raw.meta.json)
  verifier  -> state/candidates/<category>.verdicts.json  (category from the reply,
               or from the event ids in the kept files)

If the reply is not valid JSON, the hook asks the subagent once to answer again
with JSON only (decision "block"); a second failure is left to the main agent,
which falls back to `candidates.py save`. Standard library only; never raises.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path


def extract_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except ValueError:
            return None
    return None


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    tmp.replace(path)


def save_scout(cdir: Path, obj: dict, run_id: str) -> str | None:
    cat = obj.get("category")
    if not cat or not isinstance(obj.get("candidates"), list):
        return None
    meta_path = cdir / f"{cat}.raw.meta.json"
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        meta = {}
    if meta.get("run_id") != run_id:
        meta = {"run_id": run_id, "parts": {}}
    city = obj.get("city") or "?"
    meta["parts"][city] = obj  # a retry for the same city replaces its earlier reply
    meta["saved_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    parts = list(meta["parts"].values())
    merged = dict(parts[0]) if len(parts) == 1 else {
        **parts[0],
        "city": ", ".join(p.get("city", "?") for p in parts),
        "candidates": [c for p in parts for c in p.get("candidates", [])],
        "sources_checked": [s for p in parts for s in p.get("sources_checked", [])],
        "exhausted": all(p.get("exhausted", False) for p in parts),
        "notes": " | ".join(f"{p.get('city')}: {p.get('notes', '')}" for p in parts if p.get("notes")),
    }
    write(cdir / f"{cat}.raw.json", merged)
    write(meta_path, meta)
    return f"{cat}.raw.json"


def save_verifier(cdir: Path, obj: dict, run_id: str) -> str | None:
    if not isinstance(obj.get("results"), list):
        return None
    cat = obj.get("category")
    if not cat:
        ids = {r.get("event_id") for r in obj["results"]}
        for kept in cdir.glob("*.kept.json"):
            try:
                if ids & {k.get("event_id") for k in json.loads(kept.read_text())}:
                    cat = kept.name.split(".")[0]
                    break
            except (OSError, ValueError):
                continue
    if not cat:
        return None
    write(cdir / f"{cat}.verdicts.json", obj)
    write(cdir / f"{cat}.verdicts.meta.json", {"run_id": run_id,
                                               "saved_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")})
    return f"{cat}.verdicts.json"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    kind = payload.get("agent_type")
    if kind not in ("scout", "verifier"):
        return
    state_dir = Path(os.environ.get("CURATOR_STATE_DIR") or payload.get("cwd") or ".")
    cdir = state_dir / "state" / "candidates"
    run_id = os.environ.get("CURATOR_RUN_ID", "")
    obj = extract_json(payload.get("last_assistant_message", ""))
    saved = None
    try:
        if isinstance(obj, dict):
            saved = save_scout(cdir, obj, run_id) if kind == "scout" else save_verifier(cdir, obj, run_id)
    except Exception:
        saved = None
    log = state_dir / "logs" / "subagent_saves.jsonl"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps({"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "run_id": run_id,
                                "agent_type": kind, "saved": saved}) + "\n")
    except OSError:
        pass
    if saved is None and not payload.get("stop_hook_active"):
        print(json.dumps({"decision": "block", "reason":
                          "Your final reply must be exactly one JSON object in the shape your instructions give, "
                          "with no text before or after it. Reply again with only that JSON."}))


if __name__ == "__main__":
    main()
