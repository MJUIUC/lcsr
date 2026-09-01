# Design

Read [`evidence.md`](evidence.md) first. Every choice below is downstream of a
finding there, and each section names the finding it rests on.

**Status: proposal. Nothing here is implemented.**

---

## The core decision

> **The scheduled unit is a PATTERN. The retrieval item is a problem you have not
> seen. The first thing graded is whether you RECOGNISED the pattern.**

Three evidence-driven departures from "Anki for LeetCode":

| Naive design | This design | Why (evidence.md §) |
|---|---|---|
| Schedule a *problem*; re-solve it | Schedule a *pattern*; solve a **new** problem in it | §4b varied practice beats constant practice, and specifically on novel items |
| Grade "did you solve it" | Grade **recognition first**, implementation second | §4a errors under blocked practice are *strategy-selection* errors |
| Failure → try again | Failure → **study a worked solution**, then relearn | §4c worked-example effect; flailing burns working memory |
| Fixed interval ladder | **FSRS-6** memory model, refit on your data | §5 727M-review benchmark, 99.6% superiority over SM-2 |

A "pattern" is a schema with a firing condition, not a topic tag. `"Arrays"` is a
topic. `"Monotonic stack — next greater element, when you need for each element
the nearest later element beating it"` is a pattern. The firing condition is the
thing being trained, because it is the thing an interview actually tests.

---

## Data model

Storage: plain JSON under `~/.leetcode-srs/` (or `$LCSR_HOME`). Human-readable,
diffable, trivially backed up. No database.

```
Pattern
  id, name, trigger          # the firing condition, in your own words
  invariant                  # the one sentence that makes it work
  card: fsrs.Card            # D / S / R / due / state  ← the scheduled thing
  complexity                 # expected time/space, for grading recognition

Problem
  id, title, url, source     # blind75 | neetcode150 | custom
  pattern_ids: [id]          # usually 1, sometimes 2 — see "Multi-pattern"
  seen_count, last_seen
  worked_solution            # link or local note — the §4c fallback

Attempt                      # one row per review, append-only
  ts, pattern_id, problem_id
  recognition: miss|hint|clean
  implementation: fail|struggle|clean
  rating: fsrs.Rating        # derived — see truth table
  seconds_to_recognition
  predicted_retrievability   # snapshot at review time ← powers calibration
  note

ReviewLog                    # fsrs.ReviewLog, one per Attempt, for the Optimizer
```

`predicted_retrievability` is recorded **at review time and never recomputed**.
It is the only way to check the model honestly after the fact.

---

## The rating truth table

This is the crux of the whole system, so it is a **pure function**, in one place,
tested exhaustively over all nine cells:

```python
def derive_rating(recognition: Recognition, implementation: Implementation) -> Rating:
```

| recognition | implementation | rating | rationale |
|---|---|---|---|
| miss | fail | **Again** | nothing was retrieved |
| miss | struggle | **Again** | got there by search, not by schema |
| miss | clean | **Hard** | solved it, but *recognition is the target skill* |
| hint | fail | **Again** | needed the cue and still could not execute |
| hint | struggle | **Hard** | partial schema |
| hint | clean | **Hard** | execution is fine; the firing condition is not |
| clean | fail | **Hard** | schema present, implementation gap |
| clean | struggle | **Good** | the normal successful review |
| clean | clean | **Easy** | fluent |

The rows in bold-italic below are the ones that encode the scientific claim, and
the ones most likely to be argued with:

- **`miss + clean → Hard`, not Good.** You solved the problem. You still do not
  own the pattern. Under §4a this is exactly the state that collapses when
  problems arrive unlabelled.
- **`clean + fail → Hard`, not Again.** Recognition survived; only execution
  failed. Scheduling this like a total blank would waste the retrieval you *did*
  earn (§2 — the successful retrieval at low retrieval strength is the valuable
  event).

Per the standing rule on cross-file invariants: this function is pure, lives
alone, and gets a 9-case exhaustive test. Diff review does not catch a wrong cell
here — and a wrong cell silently corrupts every future interval.

---

## A review session

```
lcsr review
```

1. **Select.** Patterns whose predicted retrievability has fallen below desired
   retention. `Again`-rated patterns re-enter the same session after a relearning
   step (§4d, retrieve to criterion — "due" means *until correct once*).
2. **Interleave.** Consecutive items are never the same pattern. Order is
   shuffled, not grouped. (§4a — this is not a nicety, it is the mechanism.)
3. **Draw an instance.** Pick an **unseen** problem tagged with that pattern.
   Prefer unseen, then least-recently-seen. (§4b.) When a pattern's bank runs dry
   the CLI says so and asks you to add problems — rather than silently degrading
   to constant practice.
4. **Stage 1 — recognition, timed, no editor.** You are shown the *problem only*.
   Never the pattern name. Name the pattern, state the invariant, state expected
   complexity. Reveal, then self-grade `miss | hint | clean`.
5. **Stage 2 — implementation.** Actually solve it. Grade
   `fail | struggle | clean`.
6. **Grade + schedule.** `derive_rating`, feed `scheduler.review_card`, append
   the `Attempt` and `ReviewLog`.
7. **On `Again` → worked example.** Show the stored worked solution and require an
   explanation of *why the pattern fires here* before moving on (§4c). This
   prompt **fades once pattern stability passes a threshold** — otherwise the
   expertise-reversal effect turns the help into a tax.

**Self-rating is the sole input to the model.** Inflate it and you corrupt every
subsequent interval. This is stated in the docs and there is no streak counter,
no XP, and no daily-goal confetti to give you a reason to lie (§2).

---

## Target-date mode

The best-quantified result in the literature, and no SRS I found actually uses it.

```
lcsr target --date 2026-11-15
```

Cepeda 2008 (§1): optimal gap ≈ **20%** of the retention interval at a few weeks,
falling toward 5–10% at a year. So with `T` days until the interview:

- cap `maximum_interval` at ≈ `0.2 × T`, so nothing is scheduled to peak after
  the date that matters;
- ramp `desired_retention` upward as `T` shrinks, since post-date workload has no
  value;
- as `T → 0`, report **predicted recall per pattern on the target date** — which
  is the actual question you care about, and something FSRS can answer directly
  and SM-2 cannot.

---

## Calibration — the part that makes this falsifiable

Per §6, the honest risk is that FSRS's flashcard-fitted parameters do not
describe *schema* memory under *varied* retrieval. So the tool measures itself.

```
lcsr calibrate
```

Bins your attempts by `predicted_retrievability`, and reports predicted vs.
observed recall per bin, plus log loss and RMSE **against a trivial
"always predict the base rate" baseline**. If FSRS is not beating that baseline
on your data, the tool says so plainly instead of projecting confidence.

```
lcsr optimize
```

Runs `Optimizer.compute_optimal_parameters()` on your logs once you have enough
of them (py-fsrs guidance suggests hundreds-to-~1000 reviews; below that it
refuses rather than overfitting), plus `compute_optimal_retention()`. Writes new
parameters with the old set retained, so a refit can always be rolled back.

---

## Anti-features (deliberately excluded, with reasons)

- **No blocked drilling** ("do 10 sliding-window problems") — §4a, the condition
  that produced strategy-selection errors.
- **No re-solving a problem while unseen ones remain** — §4b, constant practice.
- **No streaks, XP, or daily goals** — they create an incentive to inflate the
  self-rating that the entire model consumes.
- **No "review early because I feel like it"** — §2, retrieval at high retrieval
  strength yields little storage gain. Early review is allowed but flagged as
  low-value, and the CLI says why.
- **No difficulty rating chosen by the user directly.** Difficulty is FSRS's
  latent parameter, inferred from grades. Letting the user set it directly would
  double-count.

---

## Stack

- **Python 3.13** — already installed at `/opt/homebrew/bin/python3.13`. Note
  system Python is 3.9.6, below py-fsrs's 3.10+ floor, so the venv must be built
  against 3.13 explicitly.
- **`fsrs`** (MIT) — the only runtime dependency that matters.
- **`rich`** — CLI rendering.
- `pytest` for tests; `ruff` for lint.
- Installed as an editable package exposing the `lcsr` command.

---

## Proposed build order

| Phase | Contents | Why first |
|---|---|---|
| 1 | Storage layer, `derive_rating` + its 9-case exhaustive test, FSRS wiring | The truth table is the highest-risk-per-line code in the repo |
| 2 | `lcsr review` — the two-stage interleaved session | The core loop |
| 3 | Pattern/problem seeding: Blind 75 and NeetCode 150 mapped **to patterns**, which is manual curation work and the real cost of this project | Nothing works without a pattern-tagged bank |
| 4 | `lcsr calibrate` | Makes phases 1–3 checkable rather than assumed |
| 5 | `lcsr target`, `lcsr optimize`, stats | Refinement |

**Phase 3 is the honest bottleneck.** Tagging ~150 problems with genuine firing
conditions is hours of judgement work, not code, and it cannot be fully automated
without producing exactly the useless topic tags this design rejects. Worth
deciding up front whether you want to curate that yourself, have me draft it for
your review, or start with a much smaller hand-picked set of ~20 patterns.

---

## Open questions for you

1. **Pattern bank**: curate yourself, have me draft it, or start small (~20)?
2. **Target date** — is there a real interview date to aim at, or is this
   open-ended maintenance? It changes the scheduler defaults materially.
3. **Stage 2 friction**: does the tool just link out to LeetCode and take your
   word for the result, or do you want local solution files tracked in the repo?
4. **Desired retention**: start at py-fsrs's 0.90, or lower (~0.85) to cut
   workload until there is enough data to compute your own optimum?
