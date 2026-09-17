# lcsr: LeetCode Spaced Repetition

> Forked from [Swapnil-jain/lcsr](https://github.com/Swapnil-jain/lcsr) — original browser-based tool by Swapnil Jain.
> This fork by [MJUIUC](https://github.com/MJUIUC) adds a native desktop app, a timer-governed practice loop,
> an enriched cue table, and a redesigned card UI.

---

**A spaced repetition system for LeetCode and DSA interview prep.**

**Miss a problem and it comes back in 3 days, then 10, then 30. Solve it cold and
it never comes back at all.** Fail it again at any rung and you drop to the
bottom, because the point is to re-earn the spacing, not to resume it.

That schedule runs over 324 problems in a fixed order, taken from an 18-week
data structures and algorithms curriculum, plus a 44-entry pattern cue table.

---

## What this fork adds

### Native desktop app (`lcsr app`)

The original tool runs as a local web server you open in a browser. This fork
adds `lcsr app` — a native desktop window built with
[pywebview](https://pywebview.app) that runs the same UI without a browser,
enabling features that the browser's security model prevents:

- **Reliable alarm audio** — the timer plays a buzzer the moment it hits zero,
  no user gesture required (browsers block this)
- **Window focus** — the app snaps into focus after the timer closes
- **Direct Python calls** — the UI talks to the backend directly instead of
  over HTTP, removing the server entirely from the desktop path

### Timer-governed outcomes

The original tool is self-report: you click Solved or Stuck after attempting a
problem. This fork replaces that with a **timed practice loop**:

1. Expand a problem card to read the description (fetched live from LeetCode)
2. Click **Start timed attempt** — the timer popup opens and LeetCode opens in
   your real browser simultaneously
3. **Done** before the timer runs out → logged as solved immediately
4. **I'm Stuck** or timer reaches zero → alarm fires, app comes to focus,
   stuck panel opens with a YouTube solutions link, no way to self-report solved

The timer is the authority. There is no Solved button on the card.

### Redesigned card UI

- Cards expand to show the problem description, tier, LeetCode link, and cue
- The cue text links directly to the matching entry in the Cue table
- Solved cards are inert — once done, move on
- Skip removed — the timer governs, not avoidance

### Enriched cue table

The 20-row cue table from the curriculum is extended to 44 entries:

- Every entry has a `because` field explaining *why* the pattern is correct,
  often contrasting the wrong approach
- Every entry has 2–3 hand-curated related problems from the curriculum
- `cue_map.json` maps all 314 curriculum problems to their cue entries —
  the source of truth for the problem→pattern relationship
- The cue table is searchable and accordion-style; collapsed cards hide the
  pattern name so you can practice recognition before revealing

---

## Install

**CLI + browser UI (original flow, no extra dependencies):**

```bash
git clone https://github.com/MJUIUC/lcsr && cd lcsr
python3 -m venv .venv && .venv/bin/pip install -e .
```

Python 3.10+. No dependencies for the base install.

**Desktop app (this fork's main addition):**

```bash
.venv/bin/pip install -e ".[app]"
```

This adds `pywebview` and `youtube-search-python`.

---

## Launch

### Desktop app (recommended)

```bash
lcsr app
```

Opens a native window with the full UI. No browser needed. LeetCode problems
open in your real browser when you start a timed attempt.

### Browser-based (original flow)

```bash
lcsr up            # start in background, open browser tab
lcsr status        # is it running?
lcsr down          # stop it
lcsr serve         # foreground, with logs
```

---

## How the timer works

1. Open a problem card (click the header to expand)
2. Read the description, recall the cue
3. Click **Start timed attempt** — timer popup opens, LeetCode opens in browser
4. On the timer:
   - **Pause** — freeze the clock once per attempt
   - **Done** — solved before the buzzer; logged immediately, app comes to focus
   - **I'm Stuck** — declare stuck early; no alarm, timer closes, stuck panel opens
   - **Natural timeout** — alarm fires, timer closes, stuck panel opens
5. On the stuck panel:
   - **View solutions on YouTube** link (highlighted)
   - Pick a mistake class, add a note
   - **Log as stuck** — returns in 3 days, then 10, then 30

Timer length defaults to 25 minutes (the curriculum's own number). Change it
in **Settings → Timed attempts**.

---

## CLI

The CLI is unchanged from the original:

```bash
lcsr today                       # due re-solves first, then today's new problems
lcsr show 42                     # the cue and the link
lcsr log 42                      # solved it cold
lcsr log 42 --stuck --mistake invariant
lcsr log 1 217 242 --date yesterday
lcsr amend 15 --stuck --mistake no-pattern
lcsr undo 209                    # retract the most recent attempt
lcsr stats                       # the three metrics
lcsr cues                        # self-test the cue table; --answers to check
lcsr week 5                      # one week's blocks, with progress
lcsr config                      # show the daily load
lcsr config --core 3 --total 5   # change it
lcsr sprint                      # start another pass over the curriculum
lcsr export --out progress.csv
```

Mistake classes: `off-by-one`, `invariant`, `edge-case`, `no-pattern`.

---

## What is stored where

| File | Contents |
|---|---|
| `~/.lcsr/log.jsonl` | Append-only attempt log — the only record |
| `~/.lcsr/settings.json` | Daily load overrides |
| `~/.lcsr/prefs.json` | UI preferences (timer length) |
| `~/.lcsr/problem_cache.json` | Cached problem descriptions from LeetCode |
| `~/.lcsr/custom.json` | Problems added via `lcsr add` |

The log is append-only. Undo and amend append a retraction rather than deleting
a line. Everything — due dates, metrics, schedule — is recomputed from it on
each run.

---

## Data files

See [`src/lcsr/data/README.md`](src/lcsr/data/README.md) for documentation of
all bundled data files (`problems.json`, `cues.json`, `cue_map.json`, etc.),
their schemas, and how they relate to each other.

---

## How it works

`lcsr serve` / `lcsr app` both use the same backend: `src/lcsr/schedule.py`
(one pure function, exhaustively tested), `src/lcsr/store.py` (log I/O), and
`src/lcsr/plan.py` (what to show today). The desktop app replaces HTTP calls
with direct Python method calls via pywebview's JS bridge. The log format is
identical regardless of which frontend you use.

---

## Credits

The curriculum is not mine or Swapnil's. The 18-week structure, the problem
ordering, the cue table, and the block titles come from a third-party document,
`DSA-Curriculum-18-Week.pdf`. `src/lcsr/data/problems.json` and `cues.json` are
extracted from it by `tools/parse_curriculum.py`. The `because` field
explanations and `cue_map.json` associations in this fork were written by
[MJUIUC](https://github.com/MJUIUC).

Problem titles and links belong to LeetCode.

The original tool was built by [Swapnil Jain](https://github.com/Swapnil-jain).
This fork would not exist without it.

---

Made with love by [MJUIUC](https://github.com/MJUIUC)
· [GitHub](https://github.com/MJUIUC/lcsr)
· Forked from [Swapnil-jain/lcsr](https://github.com/Swapnil-jain/lcsr)
