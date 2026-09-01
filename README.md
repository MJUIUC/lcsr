# lcsr

Runs the daily loop from `DSA-Curriculum-18-Week.pdf` and records it. All 314
problems, the 20-row cue table, and the curriculum's `+3d / +10d / +30d`
re-solve rule for problems you got stuck on.

It does not invent a study method. The curriculum has one; this makes following
it cost nothing.

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
lcsr serve                       # the UI — opens http://127.0.0.1:8765
```

The page shows due re-solves first, then today's new problems. Each row links to
LeetCode, and marks **Solved** or **Stuck**; stuck opens a mistake class and a
note field. Nothing is stored in the browser — every action appends to the same
log the CLI reads.

### Adding problems

In the UI, "Add a problem" at the bottom. Or:

```bash
lcsr add 1768 "Merge Strings Alternately" --block Warmup --cue "two strings, alternate"
```

Additions go to `~/.lcsr/custom.json`, kept separate from the packaged
curriculum so upgrades never overwrite them, and appear under "Added". A custom
entry reusing a packaged id overrides it — that is how you re-week or retag a
problem without editing packaged data.

### CLI

```bash
lcsr today                       # due re-solves first, then today's new problems
lcsr show 42                     # the cue and the link — but not the pattern name
lcsr log 42                      # solved it cold
lcsr log 42 --stuck --mistake invariant
lcsr log 1 217 242 --date yesterday
lcsr undo 209                    # retract the most recent attempt
lcsr stats                       # the three metrics the curriculum names
lcsr cues                        # self-test the cue table; --answers to check
lcsr week 5                      # one week's blocks, with progress
```

Mistake classes: `off-by-one`, `invariant`, `edge-case`, `no-pattern`.

## How it works

`~/.lcsr/log.jsonl` is append-only and is the only record. Undo appends a
retraction rather than deleting a line, so a mis-logged attempt is recoverable
and the record of what happened is never rewritten underneath you. Due dates, boxes and
every metric are recomputed from it on each run, so nothing can drift out of
sync and the scheduling rule can change later without invalidating history.

`lcsr serve` binds to loopback only and has no auth — it is a local tool.

Scheduling is `src/lcsr/schedule.py` — one pure function, with an exhaustive
truth table over all 8 states in `tests/test_schedule.py`.

There is no streak counter and no problems-solved metric. The curriculum names
that one as the weakest predictor of interview performance, and the easiest to
inflate.

## The frequently-asked pool

A separate **Frequent** tab: 363 unique problems merged from Top Interview 150,
LeetCode 75, Top 100 Liked and Striver's A2Z, with a weighted lucky draw.

It is deliberately *not* merged into the curriculum — it does not change the
322 totals or any metric. The only crossing point is read-only: each problem
shows whether it is already in your curriculum and whether you have logged it,
so a draw can skip what you have covered.

Deduplication is by LeetCode frontend id, the only stable key (titles repeat,
slugs change). 599 raw entries collapse to 363: A2Z alone lists 18 problems
under two topics, and the four lists overlap heavily.

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

- [`docs/evidence.md`](docs/evidence.md) — the literature review this started from
- [`docs/design.md`](docs/design.md) — what was built and what was dropped
