## Analysis (written by hand, appended to the generated report)

### Headline (five evaluation cases, 3 runs each, model `claude-opus-5` for both)

| | Baseline | Improved |
|---|---|---|
| Cases passed | 12/15 (case 1: 0/3) | **15/15** |
| Rule violations per run | 0.2 | **0** |
| Invalid events booked per run | 0.2 | **0** |
| Appropriate escalations per run | 0.2 | 0.2 |
| Unnecessary escalations per run | 1.73 | **0** |
| Calendar conflicts | 0 | 0 |
| Tool calls per run (min–max) | 32 (20–42) | 99 (47–158) |
| Turns per run | 33 | 56 |
| Wall time per run | 153 s | 374 s |
| Estimated cost per run (total) | $0.77 ($11.48) | $2.91 ($43.59) |

Costs are Claude Code's local estimates at API list price; the runs drew on a Max subscription, not a bill.

### What the improvements bought

- **Memory closes the one failure the baseline cannot fix.** Case 1 fails 3/3 for the baseline because it has no history and re-books the exhibition Nicolas already attended; the improved agent's exclusion list (history + seen, with exhibition and same-talk keys) removes it before scouting, and passes 3/3.
- **Escalation discipline.** The baseline asks about 1.7 unnecessary things per run (mostly the suggested-donation gallery it wasn't going to pick anyway, plus invented profile gaps). The improved agent asked exactly the required questions (the New York tier-3 talk in case 4) and nothing else: 0 unnecessary in 15 runs. The ask-first decision is made by `rank.py` and the booking procedure, not by the model's mood.
- **Same correctness on the traps, now with evidence.** Both configurations avoid the stale event and the sold-out pick in case 5 on this mock site with a strong model. The improved agent additionally leaves a trace (goal, plan, loop, decisions with evidence links, stop reason), a bookings ledger, a history file and calendar entries, which the baseline cannot produce. The six failure probes (x1–x6) all pass; the baseline was run on one probe (x3, unclear page) and also passed it.
- **Zero violations in 21 improved runs**, including opt-ins always unchecked and no duplicate submissions.

### What the improvements cost

- About 3× the tool calls, 1.7× the turns, 2.4× the wall time and 3.8× the estimated cost per run. Roughly half the tool calls are the scouts and verifiers re-reading pages the main agent could have read itself; the verifier is the price of independence.
- **Variance is higher than the baseline's**: 47–158 tool calls versus 20–42. The low end is case 2 (AI already on the calendar, so one category is skipped before scouting). The high end is travel run 3 (158 calls, $5.32): the agent correctly ran scouts for both cities and re-verified once, but also spawned an Explore agent to read `tools/rank.py` when unsure how travel time is computed from a hotel. That subagent type was not part of the team; it is now denied in every mode (`Agent(Explore)` and the other built-in types), a hardening applied after these runs and not re-measured.
- The tool-call budget (160 weekly) was never hit; the closest run counted 100 hook-logged calls.

### Fairness and limits

- Identical model, turn cap, dollar cap, mock site, Python tools and browser for both. The baseline had the rules in plain language and a structured answer format; it lacked CLAUDE.md, subagents, skills, memory, trace and the budget hook (the empty instructions-loaded log in every baseline run is the proof).
- The mock site is small and deterministic; a strong model finds the right answer with a single prompt on four of five cases. The gap on real sites, where listings are messier and pages longer, is expected to be larger, but this evaluation does not measure it.
- Sample size is 3 runs per case; the pass rates are exact for these runs, the means are indicative.

### Baseline (frozen at git tag `baseline`) — original notes

Configuration: one `claude -p` session, model `claude-opus-5`, the rules of the brief in plain language as an appended system prompt, the same Python tools and mock-site browser as the improved agent, structured JSON answer. No `CLAUDE.md` (the `InstructionsLoaded` hook log is empty in all 15 runs), no subagents, no skills, no memory files, no trace, no budget hook.

- Case 1 failed 3/3, for one reason only: no memory. The AI pick, the deadline rule, the dinner conflict and the paid event were all handled correctly.
- Cases 2–5 passed 3/3. With the deterministic tools and a strong model the baseline reads the truthful event pages and handles the stale date, the sold-out banner and the out-of-town talk.
- Unnecessary escalations: 1.7 per run. No calendar conflicts, no double submissions, opt-ins always unchecked.
- Variance low: 20–42 tool calls, 81–267 s, $0.44–$0.99 per run. Total $11.48.
