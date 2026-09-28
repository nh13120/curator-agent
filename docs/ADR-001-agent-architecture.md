# ADR-001: Curator runs as a Claude Code agent with read-only subagents and code-enforced modes

**Status:** Accepted (Phase 1 built on it)
**Date:** 2026-09-26
**Deciders:** Nicolas (owner). Recorded by Claude Code.

## Context

Curator must book free AI and art events every week, on a schedule, with real side effects (RSVP forms, Google Calendar writes, Telegram messages). It was built to six requirements set at the start: meaningful tool use, persistent memory, an observable loop with a stopping condition, a subagent team, failure recovery, and a baseline-vs-improved evaluation.

Forces that shaped the decision:

- Most of the work should be configuration, not code, and Nicolas is a Python beginner. Anything he cannot read, he cannot defend.
- Side effects are irreversible and personal. A wrong booking registers a real person; a wrong calendar write lands on a real calendar. Dry-run and fixture modes must be impossible to bypass from a prompt.
- The evaluation needs 30 repeatable headless runs that never touch real sites, plus a fair baseline with the same tools.
- Claude Code here is authenticated with a claude.ai Max subscription, not an API key. Some headless options (`--bare`) skip OAuth entirely.
- Web pages are untrusted input. The scout reads pages that may contain instructions aimed at the agent.
- A Python orchestrator on the Claude Agent SDK was a live alternative (Nicolas had seen the pattern before).

## Decision

Run Curator inside Claude Code itself. Behavior lives in `CLAUDE.md`, two subagent definitions under `.claude/agents/`, skills under `.claude/skills/`, and hooks plus permissions in `.claude/settings.json`. Small Python scripts under `tools/` are the only code, and each is a stateless CLI that prints one JSON object.

Three sub-decisions make this safe and testable:

1. **Modes are enforced in the tools.** `tools/_common.py` reads `CURATOR_MODE` and its `require_write()` refuses every side effect unless the mode is `live`, logging the blocked attempt. Playwright MCP is launched with `--allowed-origins` pinned to localhost in fixture mode, and a `PreToolUse` hook (Phase 2) denies typing into password or card fields in every mode.
2. **The main agent is the only writer.** The scout and verifier subagents get read-only tool allowlists in their frontmatter, `omitClaudeMd`, and a hook that limits their shell use to the fetch tool. The verifier receives candidate records only, never the scout's reasoning, so its check is independent.
3. **One mock site, one checker, both configurations.** Fixture mode serves a deterministic event site with real forms that record to a file. The checker scores runs from those files, never from the agent's own claims, and the baseline uses the same tools, model and limits with the harness stripped away.

## Options Considered

### Option A: Claude Code as the runtime (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low code, medium configuration. Roughly 12 small tool scripts, 2 agents, 5 skills, 2 hooks. |
| Cost | Runs on the Max subscription. Eval capped at $6 per run by `--max-budget-usd`. |
| Scalability | Adequate. One user, two categories, a few weeks of horizon. Parallel scouts are one `Agent` call each. |
| Team familiarity | The six requirements are written in these terms. New for Nicolas, but every piece is a readable text file. |

**Pros**

- Matches the "configuration over code" requirement directly; the team, the tool bounds and the hooks are visible in the config itself.
- Subagent isolation, parallel delegation, tool allowlists, permission modes and tool-call hooks come for free.
- Headless mode (`claude -p`) gives cost, turn count and duration in its JSON result, which the eval needs.
- The baseline is the same runtime with features removed, so the comparison isolates what the harness adds.

**Cons**

- Control flow lives in prompts. Stopping conditions and retry limits must be backed by hooks and budgets, not trusted to the model.
- Baseline isolation needs care: `--bare` cannot be used with OAuth, so isolation relies on `--setting-sources`, `instructionFiles: managed-only` and `--disallowedTools Agent Skill`, and must be proven with an `InstructionsLoaded` hook.
- Project-level `permissions.allow` is ignored in headless runs of an untrusted folder; the launcher must also pass rules via `--settings`.
- The Playwright MCP server under launchd is a moving part (npx download, profile locks, headed Chrome).

### Option B: Python orchestrator on the Claude Agent SDK

| Dimension | Assessment |
|-----------|------------|
| Complexity | High. The loop, retries, subagent handoffs, trace writing and budget enforcement all become Python. |
| Cost | Needs an API key. Per-token billing, no subscription. |
| Scalability | Best control over parallelism and state, but nothing here needs it. |
| Team familiarity | Nicolas has seen the pattern once. He would be maintaining several hundred lines of orchestration he did not write. |

**Pros**

- Deterministic control flow; stopping conditions are literal `if` statements.
- No dependency on Claude Code CLI behavior between versions.
- Easy to unit test the loop without a model.

**Cons**

- Contradicts the emphasis on configuration and makes the "lightweight agentic team" a custom implementation instead of a visible feature.
- Disables claude.ai connectors and the Max subscription in favor of API billing.
- Duplicates what Claude Code already provides: tool permissions, hooks, subagent isolation, cost accounting.
- Much more code for a beginner to read and defend.

### Option C: Single agent with the browser only (no subagents, no tools beyond Playwright)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Lowest. One prompt. |
| Cost | Highest per run: browsing listings and bios through page snapshots burns turns. |
| Scalability | Poor. Every candidate costs many browser calls; no parallel search. |
| Team familiarity | Trivial to understand. |

**Pros**

- Fastest to build; nothing to configure.
- Useful exactly as the evaluation baseline, which is what it became.

**Cons**

- Fails four of the six requirements outright (memory, team, structured loop, recovery).
- No independent verification, so a stale listing or a "free" event that asks for a card gets through.
- Side effects depend entirely on the prompt.

## Trade-off Analysis

The real choice was A versus B. B buys determinism at the price of code Nicolas cannot yet maintain, API billing, and re-implementing as custom code what should be visible as configuration. A keeps control flow in prompts, which is the weak point, so the design compensates by moving every hard limit into code that runs regardless of what the model decides: mode gates in `_common.py`, origin pinning in the browser process, field-type denial and tool-call budgets in a hook, and a checker that scores from ground-truth files. That combination gets most of B's safety with A's cost and readability.

C was rejected as the product but kept as the baseline, which turns its weaknesses into the measured gap the evaluation is about.

Two smaller trade-offs, both recorded in `DECISIONS.md`:

- **Google Calendar via a Python OAuth tool, not the claude.ai connector.** The connector is zero setup but cannot tag events with extended properties and cannot be swapped for fixture data. The tool costs a 10-minute console setup and gives one interface across all three modes.
- **Travel time by geocoded distance and a documented transit factor, not a routing API.** Deterministic in fixtures and free of keys; the upgrade path to Google Routes is a single environment variable.

## Consequences

- **Easier:** demonstrating each requirement, because the evidence is a file (agent frontmatter, hook log, trace, `expected.json`, `results.md`). Changing rules or categories, because they are YAML. Auditing what the agent did, because every side effect passes through one function that logs it.
- **Harder:** proving the model respected a soft rule that no hook enforces (for example "never book something mediocre to fill a quota"). Those rules are checked after the fact by the evaluation rather than prevented. Debugging headless runs, which requires reading `stream-json` output and the trace rather than stepping through code.
- **To revisit:** if Claude Code changes headless flags or subagent frontmatter, the eval harness and agent files need updating; the docs check at the start of each phase covers this. If eval variance turns out high, consider pinning a smaller model for scouts or lowering `--max-turns`. If Nicolas becomes comfortable with Python, a thin orchestrator around the same tools (Option B) remains possible without rewriting the tools.

## Phase 1 design review notes

Reviewed against the brief after the skeleton was built:

- **Mode plumbing** is in place and tested; the default mode is `dry`, so an unset variable cannot book anything.
- **Fixture realism** is good where it matters: stale listings versus truthful pages, a full event whose listing still says open, pre-checked opt-ins, a card-required form, and an injection paragraph. These are what separate the baseline from the improved agent.
- **Gap to close in Phase 2:** the two hooks and the guard logic do not exist yet, so nothing currently enforces the tier-3 field rule or the tool-call budget. Until then the mock site is the only place where a card field can appear.
- **Gap to close in Phase 2:** baseline isolation is designed but unproven. The first baseline run must show an empty `InstructionsLoaded` log and no `Agent` tool in the session's tool list.
- **Watch item:** the venv on this Mac was silently created against Python 3.14 by a plain `python3 -m venv`. The README now prescribes `python3.13`; launchd scripts must call the venv interpreter by absolute path.

## Action Items

1. [ ] Phase 2: implement `tools/hooks/guard.py` and `tools/hooks/log_tool_call.py`; prove baseline isolation with the `InstructionsLoaded` hook before running the 15 baseline runs.
2. [ ] Phase 2: pass permission allow rules through `--settings` in the eval harness and `bin/run.sh`, not only via `.claude/settings.json`.
3. [ ] Phase 3: pin `@playwright/mcp` to 0.0.82 and pre-warm the npx cache so the first scheduled run does not time out.
4. [ ] Phase 6: back every stopping condition with a hook or CLI budget and record the chosen limits in `DECISIONS.md`.
5. [ ] Phase 8: if run-to-run variance is high, revisit the model pin and turn limits before drawing conclusions in `eval/results.md`.
