# Design: public release

**Status: proposal. Not implemented.**

Takes the tool from "runs on Swapnil's laptop against a file in `$HOME`" to
"a stranger opens a URL and can use it". Five threads of work:

1. A stateless core, so the scheduler can run without a filesystem.
2. A Vercel deployment built on that core.
3. A LeetCode-flavoured theme with a real pitch-dark mode.
4. The Frequent tab reworked so it explains itself.
5. Naming, typography, and the removal of every em dash from user-facing text.

Today and Curriculum are explicitly **not** being redesigned. They work. The
changes that touch them are the theme, the naming, and the dashes, nothing
structural.

---

## 1. Decisions already taken

Two forks were settled before this document:

| Question | Decision |
|---|---|
| Where does a visitor's progress live? | **Their own browser.** `localStorage`, no accounts, no database. |
| Does the local CLI keep working? | **Yes, unchanged.** `lcsr up`, the jsonl log and all 70 tests keep passing. |

Everything below follows from those two.

The consequence worth stating plainly: **progress is per-browser and is lost if
the visitor clears site data.** That is the price of having no accounts, and the
UI has to say so out loud rather than let someone discover it after six weeks of
work. See §8.4.

---

## 2. The problem with deploying what exists

`store.py` reads and writes one hardcoded path:

```python
HOME = Path(os.environ.get("LCSR_HOME", Path.home() / ".lcsr"))
LOG  = HOME / "log.jsonl"
```

`curriculum.py` does the same for `custom.json`. On Vercel the filesystem is
read-only apart from `/tmp`, and `/tmp` is per-instance and evaporates. So every
write path is broken, and every read path returns an empty log for everyone.

The fix is not to special-case Vercel inside `store.py`. It is to stop
`store.py` knowing where the log lives at all.

## 3. A stateless core

Introduce a log **source**: an object that can read the record and append to it.
The file is one implementation; a list supplied by an HTTP request is another.

```python
# store.py
class FileLog:                       # exactly today's behaviour
    def read(self) -> list[dict]: ...        # LOG.read_text().split("\n")
    def append(self, entry: dict) -> None: ...  # LOG.open("a")

class MemoryLog:                     # serverless: the browser supplies the log
    def __init__(self, rows):
        self.rows, self.appended = list(rows), []
    def read(self):   return list(self.rows)
    def append(self, entry):
        self.rows.append(entry)
        self.appended.append(entry)  # what the client must persist

_SOURCE = contextvars.ContextVar("log_source", default=None)

def source():
    return _SOURCE.get() or FileLog()
```

`raw_entries()` and `append()` route through `source()`. **Nothing else in
`store.py`, `plan.py` or `schedule.py` changes.** Sorting, retraction handling,
replay, the ladder and all three metrics keep operating on a list of dicts,
which is what they already did.

A `contextvars.ContextVar` rather than a global: it is per-thread and per-task,
so the threaded local server and a serverless invocation both get isolation
without a lock. The default of `None` resolving to `FileLog` means the CLI needs
no changes whatsoever.

`custom.json` gets the same treatment, since `cur.add()` also writes to disk.

### 3.1 The client is the store of record

On the deployed build, the browser holds the log and posts it with every
request. The server derives and returns; it never retains.

```
POST /api/plan   {state:{log,custom}, date}     -> plan
POST /api/log    {state, id, outcome, mistake}  -> {append:[entry], plan}
POST /api/amend  {state, id, outcome}           -> {append:[undo, replacement], plan}
POST /api/undo   {state, id}                    -> {append:[undo], plan}
```

Writes return **the records to append** rather than the new state. The client
appends them to its `localStorage` log and re-persists. This keeps the
append-only property that the whole design rests on: the browser accumulates the
same jsonl the file did, retraction records and all, so a visitor can export it
and feed it straight to the CLI.

> **Gotcha to comment at the breaking site.** `LOCK` in `store.py` exists because
> the local server is threaded. Under `MemoryLog` it guards a list that is
> private to one request and is therefore pointless but harmless. It must not be
> removed: the CLI and `lcsr serve` still need it. This is exactly the kind of
> thing that reads as dead code to the next person.

### 3.2 What this costs

The log is 12 KB after 90 attempts, so posting it per request is not a concern
at any plausible size. A cap (say 2 MB, rejecting above it) goes in with the
existing `Content-Length` guard.

### 3.3 Testing

The `MemoryLog` is a better test fixture than the tmpdir monkeypatching the
suite does now, so the existing tests gain from it. New tests:

- the same log produces an identical plan through `FileLog` and `MemoryLog`
  (the property that makes one scheduler serve two front doors);
- a write returns append records that, replayed, reproduce the server's state;
- a malformed client-supplied log is rejected with the same named-line error the
  file path gives, not a 500.

---

## 4. Vercel

```
api/index.py        one Python function, exports `handler`
public/index.html   the UI, copied from src at build time
vercel.json         rewrites + includeFiles
requirements.txt    empty; the package has no dependencies
```

`api/index.py` subclasses `BaseHTTPRequestHandler`, which is the shape Vercel's
Python runtime takes directly, and which `server.py` already uses. The routing
and validation logic is shared with the local server rather than duplicated.

The package is 472 KB including all data, far inside the bundle limit.

**One source file for the UI.** `index.html` stays at
`src/lcsr/static/index.html` and a `vercel-build` step copies it into `public/`.
Two copies of a 900-line file that drift apart is a worse outcome than a
three-line build script.

**Open item to verify before building:** the exact `includeFiles` glob needed to
pull `src/lcsr/data/*.json` into the function bundle. This is the one part of
the deploy I would confirm against current Vercel docs rather than from memory.

### 4.1 Local parity

`lcsr up` keeps serving from the filesystem. The deployed build keeps serving
from the browser. Both call the same `todays_plan()`. Nothing about your 90
logged attempts changes.

---

## 5. Theme: LeetCode-flavoured, pitch dark

The current palette is a warm cream and forest green. It is nice and it is
nobody's mental model of a LeetCode tool.

**Accent** moves to LeetCode's orange `#ffa116`. The difficulty colours align to
LeetCode's own, which also means the Frequent tab's badges stop being a private
invention:

| | LeetCode | today |
|---|---|---|
| Easy | `#00b8a3` | a generic green |
| Medium | `#ffb800` | a generic amber |
| Hard | `#ff375f` | a generic red |

**Pitch dark** is a real black, not the current `#141416` charcoal:

```
--bg:#000000   --panel:#111111   --panel2:#161616   --line:#262626
--ink:#f5f5f5  --mid:#a1a1a1     --muted:#6e6e6e
```

Three deliberate details:

- Shadows do not read against pure black. The dark theme drops them and
  separates surfaces with borders instead.
- `#ffa116` on `#000000` clears 4.5:1, so the accent can carry text, not just
  fills.
- Orange on black is the one combination where a hairline border beats a glow.

**A real theme toggle.** Today the theme is `prefers-color-scheme` only, so
someone whose OS is in light mode cannot see the pitch dark at all, which is
the mode being asked for. Adds a three-way control (system / light / dark) in
the header, persisted to `localStorage`, stamping `data-theme` on `<html>`.
Every token is defined on bare `:root` and redefined under both
`@media (prefers-color-scheme: dark)` and `:root[data-theme="dark"]`, so the
toggle wins in both directions.

---

## 6. Naming: the full form in the navbar and the footer

`lc<em>sr</em>` in the header is a wordmark that means nothing to a first-time
visitor. The navbar gets the full name alongside it, and the footer repeats it
with the one-line description:

```
header   LeetCode Spaced Repetition        [lcsr]
footer   LeetCode Spaced Repetition · runs the daily loop from the
         18-week DSA curriculum and records it.
```

> **Assumption, easy to change:** that `lcsr` expands to *LeetCode Spaced
> Repetition*. It is what the repo name and the tool's behaviour imply, but it
> has never been written down anywhere, so say the word if it should be
> something else.

---

## 7. Frequent: the tab that does not explain itself

The brief is that it is not clear what this tab is. Reading it cold, that is
right, and for five separate reasons:

| Problem | Why it lands badly |
|---|---|
| The label is an adjective | "Frequent" what? Every other tab is a noun. |
| It looks identical to Curriculum | Same green, same cards, same rows, so it reads as more curriculum. |
| The one-line hint does the whole job | "363 unique problems merged from four lists" is the entire explanation and it sits in 12.5px grey. |
| `4/4` is unexplained | The badge is the most important signal on the page and never says what it counts. |
| The draw arrives before the concept | The first thing you see is a lucky-dip button for a pool you have not been told about. |

### 7.1 The fix

**Rename it.** "Frequent" becomes **Interview pool**. A noun, and it says what
the problems have in common.

**Give it its own identity.** The tab switches the accent to a distinct hue for
its whole surface. Crossing into it should feel like leaving the curriculum,
because that separation is the single most important fact about it. Same
components, different colour, one line of CSS custom-property override on the
container.

**Lead with an explainer panel**, above the draw, not below it:

> **363 problems that interviews actually repeat**, merged from four public
> lists. This is a **browsing and practice pool, separate from your 18-week
> curriculum**: drawing from it never changes your progress, your totals, or
> any of the three metrics. 227 of these are already in your curriculum, and
> each row tells you which.

**Make the four lists first-class.** They are the entire provenance of the pool
and right now they are four unlabelled badges. Name them in the explainer, give
them a filter row of their own, and show each problem's section within the list
it came from (that data is already in `frequent.json` and is currently thrown
away).

**Explain the overlap count inline.** `4/4` becomes `on all 4 lists`, with the
count driving weight in the draw, stated where the draw is.

**Reorder the page** so concept precedes action:

```
  explainer  ->  filters  ->  draw  ->  the full list
```

Today the draw is first and the filters are third, which means the first draw
happens before you can see what you are drawing from.

---

## 8. The rest of the UI

Ordered by how much it matters for a stranger arriving at a URL.

### 8.1 There is no answer to "what is this"

The single biggest gap. Someone arriving has no idea what the 18-week
curriculum is, why problems come back after 3 days, what a cue is, or why there
is no problems-solved counter. All of that is written down already, in
`README.md` and `docs/design.md`, and none of it is in the product.

A short "How this works" panel on first visit, dismissible, plus an **About**
tab holding the longer version: the daily loop, the `+3d / +10d / +30d` rule,
the three metrics, and why the tool deliberately omits streaks.

### 8.2 The empty state is the first thing everyone sees

Every visitor starts with zero attempts, which is the one state the UI has never
really been designed for: the metrics are all em dashes, pace is blank, and the
day chip reads `day 1 · week 1 · 0/5 today`. It needs a genuine first-run view
that says what to do next.

### 8.3 Jargon carries no explanation

`box`, `cold re-solve`, `cue`, `drift`, `reps`, `stretch`. Each is a precise
term from the curriculum and each is opaque on first read. Tooltips on first
use, and definitions in the About tab.

### 8.4 Nothing tells you where your data lives

With browser-local storage this stops being a nicety. The footer states it
plainly, and the About tab gets **Export** (download the jsonl, which the CLI
can then read) and **Import**. Export is also the honest answer to "what happens
if I clear my browser".

### 8.5 Smaller items

- **Accessibility.** Icon-only buttons (`‹`, `›`) have no accessible name; focus
  rings are inconsistent; the mistake chips are `aria-pressed` but the tab list
  is not a real tablist.
- **Sharing.** No favicon, no description, no OG image. Every share renders as a
  bare URL.
- **Mobile.** Six tabs scroll horizontally with no affordance, and the problem
  row's actions wrap under the title at narrow widths.
- **Errors.** Every failure is a 2.4-second toast, including ones that need a
  decision.

---

## 9. Em dashes

**Every user-facing em dash goes.** 18 in the UI, 9 in the README, 3 in the CLI,
plus the curriculum data.

Two cases need care rather than a blind `sed`:

**The data files.** `problems.json` holds 98, inside block titles like
`Trees I — traversal, and "return one thing, track another"`. That file is
regenerated from the PDF by `tools/parse_curriculum.py`, so a hand-edit is wiped
on the next run. The normalisation belongs **in the parser**, so regeneration
stays idempotent. `cues_extra.json` (16) and `problems_extra.json` (2) are ours
and are edited directly.

**The placeholder.** `stats` renders a bare `—` for "no value yet"
(`index.html:658,668`). That is not punctuation, it is a null, and it should
become explicit text: `not yet`.

The en dash in `weeks 17–18` is not an em dash. Flagging it because a careless
regex will eat it: numeric ranges keep their en dash unless you say otherwise.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Refactoring `store.py` breaks the record the user actively uses daily | `FileLog` is the default and is byte-identical in behaviour; the full suite must pass before anything else starts |
| Browser-local storage silently loses six weeks of work | Say it in the footer, ship Export before launch |
| Vercel `includeFiles` does not pick up the data JSON | Verify against current docs; it is the one unknown in §4 |
| Theme rewrite regresses Today and Curriculum, which are explicitly fine | Palette changes are token-only; no structural CSS edits in those views |
| A blind em-dash `sed` eats en dashes and the stats placeholder | Handled as three separate cases, §9 |

## 11. Sequencing

Each step leaves the tree working and the suite green.

1. **Stateless core.** `FileLog` / `MemoryLog`, `contextvars`, `custom.json` too.
   No behaviour change; the existing suite is the proof.
2. **Parity test.** Same log, both sources, identical plan.
3. **Vercel.** `api/index.py`, `vercel.json`, `public/`, the build step.
   Deployable at the end of this step, with the old theme.
4. **Theme.** Tokens, pitch dark, the three-way toggle.
5. **Naming and em dashes.** Navbar, footer, parser normalisation, placeholder.
6. **Interview pool.** Rename, own accent, explainer, filters, reorder.
7. **Onboarding.** About tab, first-run panel, empty state, export/import.
8. **Polish.** Accessibility, meta tags, mobile.

Steps 1 to 3 are the deployment. Steps 4 to 6 are what was asked for directly.
Step 7 is what actually determines whether a stranger understands the tool, and
I would not launch without it.

---

## 12. Open questions

1. **Does `lcsr` expand to "LeetCode Spaced Repetition"?** §6 assumes so.
2. **Which hue for the Interview pool?** It needs to be clearly not the orange
   accent and clearly not the difficulty colours. Violet is the obvious gap.
3. **Is the local CLI's `~/.lcsr` log meant to sync to the deployed site?**
   Import/export covers it manually. Anything automatic needs accounts, which
   §1 ruled out.
4. **Custom domain, or `*.vercel.app`?** Only affects the meta tags.
