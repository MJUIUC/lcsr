# lcsr: LeetCode Spaced Repetition

**A spaced repetition system for LeetCode and DSA interview prep.** Runs the
daily loop from an 18-week data structures and algorithms curriculum and records
it: 324 problems, a 20-row pattern cue table, and a `+3d / +10d / +30d` review
schedule for every problem you got stuck on.

Self-hosted, single file of state, no account, no tracking, no dependencies.
Python CLI plus a local web UI, with light and pitch-dark themes.

It does not invent a study method. The curriculum has one; this makes following
it cost nothing.

**Why spaced repetition for coding interviews.** Solving a problem once and
moving on feels productive and does not last. Re-solving the ones you failed, at
widening intervals, is what moves a pattern from "I read the solution" to "I can
reach for it cold". The schedule here is the curriculum's own, and the tool
exists so that following it costs nothing.

### What it does

- **Spaced repetition / SRS scheduling.** Failed problems return at 3, 10 and 30
  days. Solved cold, they do not return. Fail again at any rung and you drop to
  the bottom: the point is to re-earn the spacing, not resume it.
- **An 18-week DSA curriculum**, 324 problems across foundations, core, reps and
  stretch tiers, in a fixed order that teaches base patterns before hard
  variants.
- **A cue table**: what the problem *says*, mapped to the pattern to reach for.
  Self-testable, answers hidden by default.
- **An interview pool** of 390 problems merged from five well-known lists
  (below), with a weighted random draw.
- **The three metrics the curriculum names**: cold re-solve rate at 30 days,
  time to correct approach, and a mistake-class histogram. No streaks and no
  problems-solved counter, on purpose.
- **A configurable daily load**, if the curriculum's own pace is wrong for you.

### Keywords

leetcode, spaced repetition, SRS, DSA, data structures and algorithms, coding
interview preparation, technical interview prep, algorithm practice, NeetCode
150, Blind 75, LeetCode 75, Top Interview 150, Top 100 Liked, Striver A2Z,
SDE sheet, FAANG interview, active recall, retrieval practice, interleaving,
study planner, problem tracker, review scheduler, anki for leetcode, self-hosted,
python, cli, local-first, no-tracking

## Install

```bash
/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e .
```

Python 3.10+ (system Python is 3.9). No dependencies.

To get `lcsr` on your PATH:

```bash
ln -s ~/leetcode-srs/.venv/bin/lcsr /opt/homebrew/bin/lcsr
```

## Use

```bash
lcsr up            # start the UI in the background and open it
lcsr status        # is it running?
lcsr down          # stop it
```

`lcsr up` is idempotent: run it any time, it only starts a server if one is not
already listening. The process is detached into its own session, so it survives
the terminal (or the agent session) that launched it closing. Liveness is checked
by connecting to the port rather than by reading the pidfile, since a pidfile
outlives a crash and pids get reused.

`lcsr serve` still runs it in the foreground if you want the logs; background
output goes to `~/.lcsr/server.log`.

The page shows due re-solves first, then today's new problems. Each row links to
LeetCode, and marks **Solved** or **Stuck**; stuck opens a mistake class and a
note field. Nothing is stored in the browser; every action appends to the same
log the CLI reads.

### Adding problems

In the UI, "Add a problem" at the bottom. Or:

```bash
lcsr add 1768 "Merge Strings Alternately" --block Warmup --cue "two strings, alternate"
```

Additions go to `~/.lcsr/custom.json`, kept separate from the packaged
curriculum so upgrades never overwrite them, and appear under "Added". A custom
entry reusing a packaged id overrides it, which is how you re-week or retag a
problem without editing packaged data.

### CLI

```bash
lcsr today                       # due re-solves first, then today's new problems
lcsr show 42                     # the cue and the link, but not the pattern name
lcsr log 42                      # solved it cold
lcsr log 42 --stuck --mistake invariant
lcsr log 1 217 242 --date yesterday
lcsr amend 15 --stuck --mistake no-pattern   # it was not actually solved
lcsr undo 209                    # retract the most recent attempt
lcsr stats                       # the three metrics the curriculum names
lcsr cues                        # self-test the cue table; --answers to check
lcsr week 5                      # one week's blocks, with progress
lcsr config                      # show the daily load
lcsr config --core 3 --total 5   # change it; `--core default` clears one
```

Mistake classes: `off-by-one`, `invariant`, `edge-case`, `no-pattern`.

### The daily load

By default you get what the curriculum prescribes for the week you are on:
roughly 4 to 5 new problems a day in weeks 1 to 3, 3 a day after that, plus
however many re-solves fall due. Due re-solves are never capped, because the
curriculum counts them as additional and mandatory.

Change any of it in **Settings**, or from the CLI:

```bash
lcsr config --foundations 1 --core 2   # per tier
lcsr config --total 4                  # or cap the whole day
lcsr config --reset                    # back to the curriculum's own load
```

Leave a tier unset to follow the curriculum. `0` is a real instruction and stops
that tier being issued at all, which is not the same thing. When a total cap
bites, reps are cut first, then foundations, then core, which is the
curriculum's own order for when you are moving too fast.

## How it works

`~/.lcsr/log.jsonl` is append-only and is the only record. Undo and amend append a
retraction rather than deleting a line, so a mis-logged attempt is recoverable
and the record of what happened is never rewritten underneath you. An amend
keeps the original attempt's date: correcting a button-press is not the same as
working the problem again today, and re-logging would shift the due date and
consume the day's quota. Due dates, boxes and
every metric are recomputed from it on each run, so nothing can drift out of
sync and the scheduling rule can change later without invalidating history.

`lcsr serve` binds to loopback only and has no auth. It is a local tool.

Scheduling is `src/lcsr/schedule.py`: one pure function, with an exhaustive
truth table over all 8 states in `tests/test_schedule.py`.

There is no streak counter and no problems-solved metric. The curriculum names
that one as the weakest predictor of interview performance, and the easiest to
inflate.

## The interview pool

A separate **Interview pool** tab: 390 unique problems merged from five public
lists, with a weighted lucky draw.

| List | Problems |
|---|---|
| [NeetCode 150](https://neetcode.io/practice) | 150 |
| [Top Interview 150](https://leetcode.com/studyplan/top-interview-150/) | 150 |
| [Top 100 Liked](https://leetcode.com/studyplan/top-100-liked/) | 100 |
| [LeetCode 75](https://leetcode.com/studyplan/leetcode-75/) | 75 |
| [Striver A2Z](https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/) | 251 |

The draw is weighted by how many lists a problem appears on, so the eight that
all five agree about come up most and the 212 that only one list carries come up
least.

It is deliberately *not* merged into the curriculum, and it does not change the
324 totals or any metric. The only crossing point is read-only: each problem
shows whether it is already in your curriculum and whether you have logged it,
so a draw can skip what you have covered.

Deduplication is by LeetCode frontend id, the only stable key (titles repeat,
slugs change). 749 raw entries collapse to 390, because the lists overlap
heavily and A2Z files 18 problems under two to four topics each (274 entries for
251 problems).

```bash
python tools/build_frequent.py     # refetch and rebuild the pool
```

## Regenerating the curriculum

```bash
python tools/parse_curriculum.py ~/Desktop/DSA-Curriculum-18-Week.pdf
```

Asserts the tier counts still match the figures the PDF states for itself
(42/142/113/17), so a layout change in a future edition fails loudly instead of
silently producing a short list.

## Docs

- [`docs/evidence.md`](docs/evidence.md): the literature review this started from
- [`docs/design.md`](docs/design.md): what was built and what was dropped
