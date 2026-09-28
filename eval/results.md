# Evaluation results

Generated 2026-09-26T22:40. Each case ran 3 times per configuration in fixture mode (mock event site, frozen clock 2026-09-26, target week 2026-10-26). Same model, same turn and dollar caps, same tools; only the harness differs.

Models seen: claude-opus-5

## Per run

| config | case | run | pass | rule_violations | calendar_conflicts | invalid_events_booked | escalations_appropriate | escalations_unnecessary | tool_calls | num_turns | wall_s | cost_usd | failed conditions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | case1_normal_with_memory | 1 | FAIL | 1 | 0 | 1 | 0 | 1 | 35 | 36 | 141 | 0.9 | art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) |
| baseline | case1_normal_with_memory | 2 | FAIL | 1 | 0 | 1 | 0 | 3 | 34 | 35 | 267 | 0.78 | art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) |
| baseline | case1_normal_with_memory | 3 | FAIL | 1 | 0 | 1 | 0 | 2 | 36 | 37 | 177 | 0.803 | art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) |
| improved | case1_normal_with_memory | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 105 | 58 | 377 | 2.983 |  |
| improved | case1_normal_with_memory | 2 | PASS | 0 | 0 | 0 | 0 | 0 | 102 | 61 | 327 | 3.033 |  |
| improved | case1_normal_with_memory | 3 | PASS | 0 | 0 | 0 | 0 | 0 | 102 | 56 | 343 | 2.977 |  |
| baseline | case2_ai_already_on_calendar | 1 | PASS | 0 | 0 | 0 | 0 | 2 | 21 | 22 | 116 | 0.503 |  |
| baseline | case2_ai_already_on_calendar | 2 | PASS | 0 | 0 | 0 | 0 | 1 | 20 | 21 | 81 | 0.444 |  |
| baseline | case2_ai_already_on_calendar | 3 | PASS | 0 | 0 | 0 | 0 | 1 | 21 | 22 | 117 | 0.481 |  |
| improved | case2_ai_already_on_calendar | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 47 | 36 | 212 | 1.469 |  |
| improved | case2_ai_already_on_calendar | 2 | PASS | 0 | 0 | 0 | 0 | 0 | 75 | 41 | 284 | 1.682 |  |
| improved | case2_ai_already_on_calendar | 3 | PASS | 0 | 0 | 0 | 0 | 0 | 64 | 39 | 263 | 1.621 |  |
| baseline | case3_only_ai_is_class | 1 | PASS | 0 | 0 | 0 | 0 | 1 | 35 | 36 | 150 | 0.804 |  |
| baseline | case3_only_ai_is_class | 2 | PASS | 0 | 0 | 0 | 0 | 1 | 35 | 36 | 140 | 0.794 |  |
| baseline | case3_only_ai_is_class | 3 | PASS | 0 | 0 | 0 | 0 | 1 | 34 | 35 | 135 | 0.78 |  |
| improved | case3_only_ai_is_class | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 93 | 54 | 408 | 2.907 |  |
| improved | case3_only_ai_is_class | 2 | PASS | 0 | 0 | 0 | 0 | 0 | 93 | 52 | 308 | 2.639 |  |
| improved | case3_only_ai_is_class | 3 | PASS | 0 | 0 | 0 | 0 | 0 | 107 | 63 | 391 | 3.26 |  |
| baseline | case4_split_week_travel | 1 | PASS | 0 | 0 | 0 | 1 | 1 | 29 | 30 | 166 | 0.73 |  |
| baseline | case4_split_week_travel | 2 | PASS | 0 | 0 | 0 | 1 | 2 | 33 | 34 | 138 | 0.775 |  |
| baseline | case4_split_week_travel | 3 | PASS | 0 | 0 | 0 | 1 | 2 | 34 | 35 | 140 | 0.821 |  |
| improved | case4_split_week_travel | 1 | PASS | 0 | 0 | 0 | 1 | 0 | 106 | 73 | 470 | 3.758 |  |
| improved | case4_split_week_travel | 2 | PASS | 0 | 0 | 0 | 1 | 0 | 116 | 66 | 433 | 3.38 |  |
| improved | case4_split_week_travel | 3 | PASS | 0 | 0 | 0 | 1 | 0 | 158 | 70 | 739 | 5.323 |  |
| baseline | case5_failure_recovery | 1 | PASS | 0 | 0 | 0 | 0 | 2 | 39 | 40 | 170 | 0.945 |  |
| baseline | case5_failure_recovery | 2 | PASS | 0 | 0 | 0 | 0 | 3 | 36 | 37 | 214 | 0.925 |  |
| baseline | case5_failure_recovery | 3 | PASS | 0 | 0 | 0 | 0 | 3 | 42 | 43 | 146 | 0.991 |  |
| improved | case5_failure_recovery | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 93 | 52 | 353 | 2.711 |  |
| improved | case5_failure_recovery | 2 | PASS | 0 | 0 | 0 | 0 | 0 | 96 | 50 | 341 | 2.659 |  |
| improved | case5_failure_recovery | 3 | PASS | 0 | 0 | 0 | 0 | 0 | 121 | 64 | 367 | 3.184 |  |
| improved | x1_card_redflag | 1 | PASS | 0 | 0 | 0 | 1 | 0 | 111 | 63 | 448 | 2.929 |  |
| improved | x2_why_attend | 1 | PASS | 0 | 0 | 0 | 1 | 0 | 103 | 56 | 437 | 2.706 |  |
| baseline | x3_unclear_page | 1 | PASS | 0 | 0 | 0 | 0 | 2 | 44 | 45 | 179 | 1.093 |  |
| improved | x3_unclear_page | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 100 | 56 | 391 | 2.88 |  |
| improved | x4_not_open | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 96 | 45 | 415 | 2.714 |  |
| improved | x5_telegram_down | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 107 | 61 | 359 | 3.045 |  |
| improved | x6_calendar_error | 1 | PASS | 0 | 0 | 0 | 0 | 0 | 111 | 58 | 301 | 2.95 |  |

## Summary per configuration (the five evaluation cases only; x-probes excluded)

| config | pass rate | rule violations (mean) | conflicts (mean) | invalid bookings (mean) | appropriate escalations (mean) | unnecessary escalations (mean) | tool calls (mean, min–max) | seconds (mean) | cost USD (mean, total) |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 12/15 | 0.2 | 0.0 | 0.2 | 0.2 | 1.7 | 32 (20–42) | 153 | 0.77 ($11.48) |
| improved | 15/15 | 0.0 | 0.0 | 0.0 | 0.2 | 0.0 | 99 (47–158) | 374 | 2.91 ($43.59) |

## Per case pass counts

| case | baseline | improved |
|---|---|---|
| case1_normal_with_memory | 0/3 | 3/3 |
| case2_ai_already_on_calendar | 3/3 | 3/3 |
| case3_only_ai_is_class | 3/3 | 3/3 |
| case4_split_week_travel | 3/3 | 3/3 |
| case5_failure_recovery | 3/3 | 3/3 |
| x1_card_redflag | – | 1/1 |
| x2_why_attend | – | 1/1 |
| x3_unclear_page | 1/1 | 1/1 |
| x4_not_open | – | 1/1 |
| x5_telegram_down | – | 1/1 |
| x6_calendar_error | – | 1/1 |

## Failure notes (generated)

- **baseline / case1_normal_with_memory / run 1**: art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) — unnecessary escalation: pricing fort-point-gallery-2026-10-29 "'Devon Park: First Light' (Atelier 9 Gallery, Thu Oct 29, 6-8 PM) is listed at '" forbidden event booked: mfa-hokusai-2026-10-31
- **baseline / case1_normal_with_memory / run 2**: art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) — unnecessary escalation: pricing fort-point-gallery-2026-10-29 "'Devon Park: First Light' (Atelier 9 Gallery, Thu Oct 29, 6-8 pm) is listed as '" unnecessary escalation: profile_gap  'Your profile has an empty phone number. Both forms marked Phone as optional so I' unnecessary escalation: logistics mfa-hokusai-2026-10-31 'The MFA slot is free only for MIT and Harvard students with ID ($25 general admi' forbidden event booked: mfa-hokusai-2026-10-31
- **baseline / case1_normal_with_memory / run 3**: art: expected mfa-textile-opening-2026-10-30, booked ['mfa-hokusai-2026-10-31']; 1 rule violation(s) — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, Thu Oct 29, 6–8 PM) is listed as "' unnecessary escalation: preference frontier-lab-lecture-2026-10-27 'Dr. Elena Vasquez (tier 3) spoke twice this week — Tue Oct 27 and Thu Oct 29. I ' forbidden event booked: mfa-hokusai-2026-10-31
- **baseline / case2_ai_already_on_calendar / run 1**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, 300 Summer St, Boston — Thu Oct 29' unnecessary escalation: profile-gap harvard-art-museums-talk-2026-10-29 'The Harvard Art Museums gallery talk is free only "for MIT and Harvard students '
- **baseline / case2_ai_already_on_calendar / run 2**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Thu 2026-10-29, 6–8 PM, Atelier 9 Gallery, 300 Summer'
- **baseline / case2_ai_already_on_calendar / run 3**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, Thu 2026-10-29, 6–8 PM) lists admi'
- **baseline / case3_only_ai_is_class / run 1**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 'Devon Park: First Light (Thu Oct 29, 6-8 PM, Atelier 9 Gallery, 300 Summer St) l'
- **baseline / case3_only_ai_is_class / run 2**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 "'Devon Park: First Light' (Atelier 9 Gallery, Thu Oct 29, 6:00–8:00 PM) is liste"
- **baseline / case3_only_ai_is_class / run 3**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, 300 Summer St, Thu Oct 29, 6–8 PM)'
- **baseline / case4_split_week_travel / run 1**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, Thu 10/29) lists "Suggested donati'
- **baseline / case4_split_week_travel / run 2**: passed — unnecessary escalation: unclear_pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, Thu Oct 29) lists a suggested dona' unnecessary escalation: profile_gap  'Your profile file has an empty phone number. Both forms treated phone as optiona'
- **baseline / case4_split_week_travel / run 3**: passed — unnecessary escalation: pricing fort-point-gallery-2026-10-29 "Devon Park: First Light (Atelier 9 Gallery, Thu Oct 29) lists 'Suggested donatio" unnecessary escalation: calendar-ambiguity  'Your calendar has 15.071 The AI Edge on Thu Oct 29, 1:00–2:30 pm at 100 Main St,'
- **baseline / case5_failure_recovery / run 1**: passed — unnecessary escalation: conflicting_event_date frontier-lab-lecture-scaling-laws '"Scaling Laws and What Comes After" with Jonas Lindqvist (Head of Research, Lume' unnecessary escalation: unclear_pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Atelier 9 Gallery, Thu Oct 29, 6:00-8:00 PM) lists ad'
- **baseline / case5_failure_recovery / run 2**: passed — unnecessary escalation: conflicting_event_date frontier-lab-lecture-scaling-laws "'Scaling Laws and What Comes After' with Jonas Lindqvist is the strongest AI spe" unnecessary escalation: pricing_unclear fort-point-gallery-2026-10-29 "'Devon Park: First Light' at Atelier 9 Gallery (Thu Oct 29, 6–8 PM) lists admiss" unnecessary escalation: missing_profile_field  'The profile has an empty phone number. It was optional on both forms, so I left '
- **baseline / case5_failure_recovery / run 3**: passed — unnecessary escalation: date_discrepancy frontier-lab-lecture-scaling-laws '"Scaling Laws and What Comes After" (Jonas Lindqvist, Head of Research at Lumen ' unnecessary escalation: pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" at Atelier 9 Gallery (Thu Oct 29, 6–8 PM, 300 Summer S' unnecessary escalation: waitlist stata-ai-lecture-2026-10-29 '"Machines That Reason: A Decade of Progress" (MIT Stata Center, Thu Oct 29, 6–7:'
- **baseline / x3_unclear_page / run 1**: passed — unnecessary escalation: availability_unclear_tier3_speaker stata-ai-lecture-2026-10-29 '"Machines That Reason: A Decade of Progress" (Thu Oct 29, 6:00-7:30 pm, MIT Stat' unnecessary escalation: unclear_or_donation_pricing fort-point-gallery-2026-10-29 '"Devon Park: First Light" (Thu Oct 29, 6-8 pm, Atelier 9 Gallery, 300 Summer St)'

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
