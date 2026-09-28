"""InstructionsLoaded hook: record which CLAUDE.md / rules files were loaded.

Used as evidence that the baseline configuration ran with no project
instructions (its log stays empty) while the improved configuration loaded
CLAUDE.md. Appends to $CURATOR_STATE_DIR/logs/instructions_loaded.jsonl.
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    state_dir = Path(os.environ.get("CURATOR_STATE_DIR") or payload.get("cwd") or ".")
    row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "file_path": payload.get("file_path"), "memory_type": payload.get("memory_type"),
           "load_reason": payload.get("load_reason"), "agent_type": payload.get("agent_type")}
    try:
        log = state_dir / "logs" / "instructions_loaded.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
