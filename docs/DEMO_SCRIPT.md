# Demo video script (60–90 s)

## Live demo on real websites (chosen by Nicolas)

Same agent as production, one week, real bookings under your signed-in browser profile.

1. Sign in once: `bin/browser-login.sh` → sign in to Luma (and Eventbrite if you want), quit Chrome. Curator books Luma events itself; Eventbrite ones arrive as a link for you.
2. Preview the week without writing anything (~10 min): `bin/demo-live.sh dry 2026-09-28 luma-boston`. The third argument restricts the scouts to Luma, the platform Curator registers on, so the take shows a real form being filled; without it the best pick is often a drop-in exhibition or a university seminar with no form. **Use the coming week:** luma.com/boston lists only the next five or so days, so a Luma-only search for a later week finds nothing (the Oct 5 preview came back empty for that reason). The preview starts from a fresh copy of the live state and memory, so it shows what the live take would do. Read `dryrun/logs/runs/demo-dry.md`: it says what would be booked and what would be asked.
3. The take: Tab 2 `bin/demo-cues.sh live`; Tab 1 `bin/demo-live.sh live 2026-09-28 luma-boston`. VS Code on `logs/runs/demo-live.md`. Record the three takes at the cues (below). Each take gets its own run id, so a retake starts with a fresh tool-call budget and an empty trace. Real Telegram messages and calendar entries appear as part of this run, so take 3 needs no cut from an older run.
4. Afterwards, whatever it booked is a real registration: keep it or cancel it (Luma: "Can't make it?" in the confirmation email, or through the site once signed in).


One recorded run of `bin/demo.sh` (about 6 minutes), cut to 90 seconds. Fixture case 5: the top AI pick is sold out while the listing still says open, and a stale past-dated event is listed as upcoming. The agent must reject the stale one and book the backup. Nothing real is touched.

## Recording in three short takes (no speed-ups, 90 s total)

The run takes about 6 minutes; you record only three moments and join the clips.

1. Open two Terminal tabs in the project. Tab 2: `bin/demo-cues.sh` (it announces "scouts", "browser", "booked", "done" out loud and prints the time).
2. **Take 1 (25 s):** Cmd-Shift-5 → record. Tab 1: `bin/demo.sh`. Watch `demo.md` fill in (Goal, Plan, two scouts). Stop at the "scouts" cue.
3. **Take 2 (45 s):** at the "browser" cue, record. Chrome fills the form, unticks the marketing boxes, submits, confirmation page; then the trace's Stop reason. Stop at "done".
4. **Take 3 (15 s):** after the run, record Telegram (real "Booked" + summary from the live run) and Google Calendar.
5. Join: open take 1 in QuickTime, drag takes 2 and 3 into its window, File → Export → 1080p. Add captions in iMovie if you like.

## Before recording

1. Windows on screen: **Terminal** in the project folder (left), **VS Code** on `demo/logs/runs/demo.md` (right; it refreshes as the trace is written). Leave room for the **Chrome** window the agent opens by itself.
2. Second screen or phone: **Telegram** open on the Curator chat, **Google Calendar** on the week of Oct 26 (for the "live" cut at the end).
3. Quit any Chrome window that is using Curator's profile (the demo uses an isolated one, but keep the desktop tidy).
4. Cmd-Shift-5 → "Record Entire Screen" → Record. Then in the terminal: `bin/demo.sh`.

## Shots and captions (cut the waits, or speed them 8×)

| Time | On screen | Caption |
|---|---|---|
| 0–10 s | Terminal: type `bin/demo.sh`; the first lines print | "Curator: book the best free AI and art event of the week, safely" |
| 10–30 s | VS Code: `demo.md` fills in. Goal, Plan, then Loop lines: two `Agent` scouts launched together, `candidates.py validate`, the verifier's verdict | "Scout finds. Verifier re-checks from the page, not the listing. Main agent decides." |
| 30–55 s | Chrome opens on the mock site: registration form, fields fill from the profile, both marketing boxes stay unticked, submit, "Registration confirmed #1" | "Top pick sold out → backup booked. Stale listing rejected from its page date." |
| 55–75 s | Cut to the phone: the real "Booked" message and weekly summary from the live run; then Google Calendar with the Curator entry | "Same agent, live: Telegram and Google Calendar" |
| 75–90 s | VS Code: scroll to `## Stop reason` → `all_slots_resolved`; beside it `eval/results.md`: baseline 12/15, improved 15/15, 0 violations | "Baseline 12/15 → improved 15/15. Zero rule violations. Every run leaves a trace." |

## Trimming

QuickTime: open the recording, Cmd-T to trim, Edit → Split Clip at each cut. For speed-ups use iMovie (Clip → Speed → Fast 8×) or leave the cuts hard. Export at 1080p; if the file is over Canvas's limit, upload to Google Drive and put the shared link in the report.

## If something differs on the day

The run is deterministic in what it books (case 5 has passed 4/4 times), but the order of the scout and verifier calls can vary. Record the whole run and choose the moments afterwards. If the agent asks a question instead of booking (it should not in case 5), the trace still shows the reasoning; record and cut around it.
