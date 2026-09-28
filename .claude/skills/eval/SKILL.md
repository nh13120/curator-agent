---
name: eval
description: How to run Curator's evaluation (baseline vs improved on the five fixture cases) and where the results are.
disable-model-invocation: true
allowed-tools: Read, Bash(python3 eval/run_eval.py report)
---

# /eval

The evaluation launches headless `claude -p` runs, so it must be started from a terminal, not from inside this session:

```bash
cd "<repo>"
python3 eval/run_eval.py run --config improved --case all --runs 3      # or --case case5_failure_recovery --runs 1
python3 eval/run_eval.py run --config baseline --case all --runs 3      # already done, frozen at git tag baseline
python3 eval/run_eval.py report                                         # rebuilds eval/results.md
```

Each run writes `eval/runs/<config>/<case>/<n>/result.json` plus the trace, submissions and hook logs. Runs that already have a result are skipped unless `--force` is given. Any change to `eval/check.py` must be followed by `python3 eval/run_eval.py recheck --config baseline`.

Current results:

!`python3 eval/run_eval.py report | sed -n '/## Summary per configuration/,/## Failure notes/p'`

Summarize the table above for Nicolas in three or four sentences: pass rates per configuration, the main measures, and which cases still fail and why (see `eval/notes.md`).
