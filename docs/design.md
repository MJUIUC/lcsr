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
