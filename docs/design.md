# Design (simplified)

Tracks `DSA-Curriculum-18-Week.pdf`. The curriculum already prescribes its own
loop and its own spacing rule; this tool's job is to **run that loop and record
it**, not to invent a better one.

Superseded: an earlier draft scheduled *patterns* and drew a fresh unseen problem
each review. Dropped on request — repetition here is re-solving **the same
problem**, which is what the curriculum specifies. The reasoning behind the
earlier draft is kept in [`evidence.md`](evidence.md) §4b, since it is the one
place this tool knowingly departs from the strongest evidence.

**Status: proposal. Not implemented.**

---

## What the curriculum already decides for us

Taken from the PDF, not invented here:

- **Spacing:** a failed problem returns at **+3d, +10d, +30d**. Solved problems
  do not return except in the W17–18 consolidation weeks.
- **The daily loop:** name the pattern + target complexity aloud (~2 min) →
  25-minute timer, no editorial/hints/LLM → solved, or stuck → if stuck, read the
  editorial *once*, close it, walk away five minutes, re-implement from a blank
  file → log one line: the cue → the pattern, and the **mistake class**.
- **Mistake classes:** off-by-one / wrong invariant / missed edge case / didn't
  see the pattern.
- **The three metrics:** cold re-solve rate at 30 days (target > 70%), time to
  correct *approach* (target < 5 min on seen patterns by week 10), and the
  mistake-class histogram. Problems-completed is deliberately **not** tracked.

The tool adds nothing to this. It just makes the logging cost near zero, because
a loop this specific is not going to be followed by hand for four months.

## Why not FSRS

The earlier draft proposed FSRS-6. Dropped:

- It only applies to the failed subset, which is where the curriculum's fixed
  `+3/+10/+30` already puts its reviews.
- `+3/+10/+30` is an expanding schedule sitting inside the range Cepeda 2006
  supports (evidence.md §1), so the gain from a fitted model is small here.
- It is a dependency, an optimizer, and a calibration story, in exchange for that
  small gain. Not worth it at this size.

Revisit only if the failed-problem backlog gets big enough that fixed intervals
visibly misfire.

---

## Data

Curriculum (in-repo, read-only) — already extracted and verified:

```
curriculum/problems.json   314 problems: id, title, hard, tier, week, block,
                           cue, role, immediately_after_prev
curriculum/cues.json       the 20-row cue → pattern table
tools/parse_curriculum.py  regenerates both from the PDF
```

Counts reconcile exactly with the document's own: **42 foundations + 142 core +
113 reps + 17 stretch = 314**, no duplicates.

Your state (outside the repo, `~/.lcsr/`, plain JSON):

```
state.json    per problem: status, attempts[], next_due, box (0..3)
log.jsonl     append-only, one line per attempt — the only real record
```

Append-only log is the point: the three metrics are all computed from it, so
they can be recomputed differently later without losing data.

---

## Commands

```
lcsr today            # what to solve: due re-solves first, then this week's new
lcsr start <id>       # prints the cue, asks for pattern + complexity, starts 25:00
lcsr log <id> solved|stuck [--mistake off-by-one|invariant|edge-case|no-pattern]
lcsr cues             # self-test on the cue table: prompts left, you fill right
lcsr stats            # the three metrics + mistake histogram
lcsr week [n]         # show a week's blocks
```

`lcsr start` deliberately shows the **cue** and not the pattern name — that is
the whole of weeks 17–18 in miniature, and it costs nothing to do all along.

## Scheduling, in full

```
solved  → done. no re-solve. (curriculum's rule)
stuck   → box 0; due +3d
          re-solve stuck again → stays in box, due +3d
          re-solve solved      → box+1; due +10d, then +30d, then done
```

That is the entire scheduler. It is a four-line function and it gets a truth
table test over (box, outcome), because a wrong cell here is invisible in review
and silently corrupts the 30-day metric.

---

## Not doing

- No streaks, no problems-solved counter — the curriculum explicitly names that
  metric as the weakest predictor, and it is the one that tempts inflation.
- No solution storage. Write in a plain editor; the tool records outcomes only.
- No auto-fetching LeetCode. Titles + ids are enough to build the URL.

---

## Open question

Only one left: **does `lcsr start` actually run a 25-minute timer in the
terminal** (blocking, with a bell), or just record the start time and let you use
your own timer? The first is more useful and more annoying.

---

## Built: the web UI

`lcsr serve` → `http://127.0.0.1:8765`, loopback only, no auth.

The page holds **no state of its own**. It reads `/api/plan` and posts to
`/api/log`, both of which call the same `plan.py` / `store.py` functions the CLI
calls, so the two surfaces cannot disagree about what is due. Closing the tab
loses nothing.

Day-planning and metrics were moved out of `cli.py` into `plan.py` when the UI
was added, precisely so "what is due today" has one implementation rather than
one per front-end.

### Adding problems later

`~/.lcsr/custom.json`, merged over the packaged curriculum at read time:

- packaged data stays read-only, so re-running the parser or upgrading never
  clobbers your additions;
- a custom entry reusing a packaged id **overrides** it, which is how to re-week
  or retag a problem without editing extracted data;
- custom problems sort after everything packaged (`order = 10000 + id`) and
  surface in an "Added" section, so `lcsr add` can never write a row that
  nothing displays.


---

## Additions to the curriculum

Eight problems added in `src/lcsr/data/problems_extra.json`, merged over the
PDF's 314 (322 total). Kept in a second file for the same reason the cue table
is: `problems.json` is regenerated from the PDF and its parser asserts the tier
counts the document states for itself, so hand-edits there would be wiped or
would break the assertion. Neither file is user state — that is `custom.json`.

The finding behind them: in three places the curriculum includes the **advanced**
member of a pattern family while the base exemplar is missing, which inverts its
own Tier 1 rule of "one exemplar per distinct cue".

| Pattern | Was present | Added |
|---|---|---|
| Kadane / max subarray | 152 Max Product Subarray (W14 core) | **53** (W13 core, before 198), **918** (W13 rep) |
| Index-as-hash | 287 Find the Duplicate (W16 core), 41 (stretch) | **448** (W3 core), **442**, **645** (W3 reps) |
| Fast exponentiation | nothing | **50** (W16 core), **29** (W16 rep) |
| Binary search in a design problem | 704 etc. (W6) | **981** (W6 core) |

152's difficulty is that you track the running min alongside the max — an
insight that only lands if you already own the max-sum version. Likewise 287 has
both a Floyd's-cycle and an index-marking solution, and without the base pattern
only the first door is visible.

`add()` takes an explicit fractional `order` so an addition slots into the real
sequence rather than the end. This matters: the curriculum is "never reordered",
and a base exemplar appended after its own hard variant would teach backwards.

Not added, deliberately: everything in the PDF's own exclusions section (segment
trees/Fenwick, network flow, computational geometry, string automata, heavy
number theory, bitmask DP), and the LeetCode Premium problems 253 Meeting Rooms
II and 269 Alien Dictionary.

---

## Neglect: missed days, carry-forward, backlog

The daily path never exercises these; they appear only after you stop using the
tool for a while, which is exactly when a silently wrong queue does most damage.

**The daily mix follows progress, not the calendar.** `current_week()` counts
elapsed days — right for reporting, wrong for choosing what to hand you. It
reported week 6 after a five-week absence, and `allowance(6)` sets foundations to
0, so 42 unattempted foundations became **permanently unreachable**: weeks only
ever advance. `intake_week()` now derives the mix from the next unattempted core
problem, so falling behind slows the schedule rather than skipping material. The
gap between the two is reported as drift.

**New problems never stack.** A skipped day is skipped, not banked — the intake
is per-day, so three days away does not produce a quadruple-size day.

**Re-solves do carry forward, capped.** They stay due and age, ordered most
overdue first (furthest decayed, and what the schedule is most wrong about). At
most `MAX_DUE_SHOWN = 8` surface at once; the rest are counted and held back so
the day stays finishable, appearing as those clear.

**Past `BACKLOG_PAUSE = 12` outstanding, new problems stop being issued.** The
curriculum's own rule when the cold re-solve rate slips is "you are moving too
fast — cut Reps and Stretch before you cut Core, and raise the number of spaced
re-solves". Stacking new material on an unworked backlog is what makes that
number worse. A paused day is explicitly *not* a finished day.

Also closed: attempts cannot be logged for a future date, and a corrupt log line
raises an error naming the file and line rather than a bare `JSONDecodeError` —
skipping it silently would drop real attempts and change every metric.

---

## Audit fixes

A 14-agent audit (7 finders, each paired with a refute-by-default adversary)
returned 33 confirmed findings and 6 refuted. The load-bearing ones:

**A note could permanently brick the log.** `append()` terminates records with
`"\n"`, but `raw_entries()` read them back with `str.splitlines()`, which also
breaks on U+2028, U+2029, U+0085, `\v`, `\f` and `\x1c`–`\x1e`. Word emits U+2028
for a soft line break, so pasting a note from a document wrote one record and
read back two unparseable halves — killing every read path, CLI and UI, with an
error naming a line number that was not the real boundary.

**A frequent-only problem coming due killed the web UI.** `enrich()` used the
curriculum-only `url()`, while `plan["due"]` rows are built with `loggable()`,
which resolves the curriculum *or* the frequent pool. The handler thread raised,
the socket closed with zero bytes, and the page went permanently blank with no
route back to History to undo it. `do_GET` now cannot answer with a dead socket.

**28 of 322 LeetCode links were 404s.** Slugs were derived from titles, and the
curriculum abbreviates ("Maximum Depth" for "Maximum Depth of Binary Tree").
Slugs now come from LeetCode's own list, with a test cross-checking every problem
that appears in both the curriculum and the frequent pool.

**Foundations were stranded a second way.** The earlier fix moved the tier mix off
the calendar, but `intake_week()` is derived from *core* progress and
`allowance()` zeroes foundations from week 4 — so finishing weeks 1–3's core
stranded all 42 remaining foundations exactly as the calendar bug had. One tier's
progress no longer zeroes another's.

**Nothing was serialized.** The server is threaded, so two concurrent logs both
read "not yet solved", both passed the already-solved gate and both appended; two
concurrent amends each retracted what the other had already replaced. Every
read-modify-write now runs under one reentrant lock, and `custom.json` is written
atomically via a temp file and `os.replace`.

**Ordering compared timestamps as text.** `ts` carries a UTC offset, so after a
DST fall-back `01:30+01:00` sorted after `02:00+02:00` despite happening earlier
— and since a retraction cancels whatever sorts last, undo cancelled the wrong
record. Ordering is now by absolute instant.

Also: `amend()` no longer drops the note, mistake class and `approach_min` it was
not asked to change; `lcsr log 42 42` no longer slips a duplicate past the
ladder-cleared guard; cross-origin writes are refused (any page visited while
`lcsr serve` runs could otherwise POST to it); ids reject bools and fractional
floats; a typed note and a picked mistake chip survive a re-render; a double
click cannot double-log; and reloading on the Frequent tab no longer renders a
blank page.


---

## One notion of "week"

There were two, and they disagreed constantly.

**Calendar week** — elapsed days since the first attempt, over seven. **Progress
week** — where you actually are in the material. The calendar drove the labels
while progress drove the content, which produced two nonsense readings:

- Finish week 1's seven core problems in two days and every day afterwards was
  labelled *"running ahead of schedule"* — permanently, because the calendar can
  never catch up to a faster pace.
- Take five weeks off and the calendar reported week 6 while progress sat at week
  1, so the tier mix was chosen for week 6 and zeroed the foundations allowance.

The second one was a real defect and got fixed by keying the mix to progress. But
that left the calendar week doing nothing except generating the first reading —
so it is gone. `current_week()` is deleted; `intake_week()` is the only week.
Progress cannot disagree with progress.

Elapsed time is still reported, but descriptively rather than prescriptively:

- **pace** — new problems started per day over a trailing window, divided by days
  actually elapsed so a young log does not read as slow;
- **projection** — remaining required problems at that rate, and the date that
  implies (stretch is optional and custom additions are yours, so neither counts);
- **idle_days** — days since the last attempt, surfaced past three, since what
  actually grows while you are away is the re-solve backlog, not the queue.

The 18 weeks were never a deadline. They were the document's estimate at its own
stated daily load; at a different load you finish at a different date, and the
tool now just tells you which.
