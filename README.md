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
lcsr today                       # due re-solves first, then today's new problems
lcsr show 42                     # the cue and the link — but not the pattern name
lcsr log 42                      # solved it cold
lcsr log 42 --stuck --mistake invariant
lcsr log 1 217 242 --date yesterday
lcsr stats                       # the three metrics the curriculum names
lcsr cues                        # self-test the cue table; --answers to check
lcsr week 5                      # one week's blocks, with progress
```

Mistake classes: `off-by-one`, `invariant`, `edge-case`, `no-pattern`.

## How it works

`~/.lcsr/log.jsonl` is append-only and is the only record. Due dates, boxes and
every metric are recomputed from it on each run, so nothing can drift out of
sync and the scheduling rule can change later without invalidating history.

Scheduling is `src/lcsr/schedule.py` — one pure function, with an exhaustive
truth table over all 8 states in `tests/test_schedule.py`.

There is no streak counter and no problems-solved metric. The curriculum names
that one as the weakest predictor of interview performance, and the easiest to
inflate.

## Docs

- [`docs/evidence.md`](docs/evidence.md) — the literature review this started from
- [`docs/design.md`](docs/design.md) — what was built and what was dropped
