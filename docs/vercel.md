# Deploying to Vercel

**Status: proposal. Not implemented.**

Everything else from the public-release plan is built and on `main`. This is the
part that is not: making the tool run without a filesystem, and putting it on
Vercel. It supersedes the fuller design doc that PR #1 carried.

## Two decisions already taken

| Question | Decision |
|---|---|
| Where does a visitor's progress live? | **Their own browser.** `localStorage`, no accounts, no database. |
| Does the local CLI keep working? | **Yes, unchanged.** `lcsr up`, the jsonl log and the whole suite keep passing. |

The consequence, which the UI has to say out loud: **progress is per-browser and
dies with cleared site data.** That is the price of having no accounts, and
Export has to ship before launch, not after.

## The problem

Three files under `~/.lcsr/` are written at runtime, and every one of them has a
hardcoded path:

| File | Written by | Holds |
|---|---|---|
| `log.jsonl` | `store.py` | every attempt, retraction and pass marker |
| `custom.json` | `curriculum.py` | problems you added yourself |
| `settings.json` | `settings.py` | the daily-load overrides |

On Vercel the filesystem is read-only apart from `/tmp`, which is per-instance
and evaporates. Every write path is broken and every read returns empty.

`server.pid` and `server.log` are the local launcher's, and have no business on
a serverless deploy at all.

## The fix: a source, not a path

`store.py` should stop knowing where the log lives. The file is one
implementation; a list supplied by an HTTP request is another.

```python
class FileLog:                       # exactly today's behaviour
    def read(self) -> list[dict]: ...
    def append(self, entry: dict) -> None: ...

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

`raw_entries()` and `append()` route through `source()`. **Nothing in `plan.py`,
`schedule.py` or `settings.py` changes.** Replay, the ladder, retractions, pass
markers and all three metrics already operate on a list of dicts.

`custom.json` and `settings.json` get the same treatment. `settings.py` is
already most of the way there: `_file()` resolves `store.HOME` per call rather
than capturing it at import, so it follows whatever the store is pointed at.

A `ContextVar` rather than a global, because it is per-thread and per-task: the
threaded local server and a serverless invocation both get isolation without a
lock. Defaulting to `None` means the CLI needs no changes at all.

> **Gotcha to comment at the breaking site.** `LOCK` in `store.py` exists because
> `lcsr serve` is threaded. Under `MemoryLog` it guards a list private to one
> request, so it is pointless but harmless. It must not be removed: the CLI and
> the local server still need it. This is exactly the kind of thing that reads as
> dead code to the next person.

## The client is the store of record

The browser holds the state and posts it with every request. The server derives
and returns; it never retains.

```
POST /api/plan   {state, date}                  -> plan
POST /api/log    {state, id, outcome, mistake}  -> {append:[entry], plan}
POST /api/amend  {state, id, outcome}           -> {append:[undo, replacement], plan}
POST /api/undo   {state, id}                    -> {append:[undo], plan}
POST /api/sprint {state}                        -> {append:[marker], plan}
```

`state` carries all three: `{log, custom, settings}`.

Writes return **the records to append**, not the new state. The client appends
them and re-persists. This keeps the append-only property the whole design rests
on: the browser accumulates the same jsonl the file did, retractions and pass
markers included, so a visitor can export it and feed it straight to the CLI.

At 12 KB after 90 attempts, posting the log per request is not a concern at any
plausible size. A 2 MB cap goes in with the existing `Content-Length` guard.

## Layout

```
api/index.py        one Python function, exports `handler`
public/index.html   the UI, copied from src at build time
vercel.json         rewrites + includeFiles
requirements.txt    empty; the package has no dependencies
```

`api/index.py` subclasses `BaseHTTPRequestHandler`, which is the shape Vercel's
Python runtime takes and which `server.py` already uses. Routing and validation
are shared with the local server rather than duplicated.

The package is under 500 KB including all data, far inside the bundle limit.

**One source file for the UI.** `index.html` stays at `src/lcsr/static/` and a
`vercel-build` step copies it into `public/`. Two copies of a 1000-line file that
drift apart is worse than a three-line build script.

**Open item, verify before building:** the exact `includeFiles` glob needed to
pull `src/lcsr/data/*.json` into the function bundle. This is the one part I
would confirm against current Vercel docs rather than from memory.

## Testing

`MemoryLog` is a better fixture than the tmpdir monkeypatching the suite does
now, so the existing tests gain from it. New ones:

- the same log produces an identical plan through `FileLog` and `MemoryLog`,
  which is the property that lets one scheduler serve two front doors;
- a write returns append records that, replayed, reproduce the server's state;
- a malformed client-supplied log is rejected with the same named-line error the
  file path gives, not a 500.

## Risks

| Risk | Mitigation |
|---|---|
| Refactoring `store.py` breaks the record in daily use | `FileLog` is the default and byte-identical; the full suite must pass before anything else starts |
| Browser-local storage silently loses weeks of work | Say it in the footer, ship Export first (it is already built) |
| `includeFiles` misses the data JSON | Verify against current docs; the one unknown above |

## Sequencing

1. **Stateless core.** `FileLog` / `MemoryLog`, the ContextVar, all three state
   files. No behaviour change; the existing suite is the proof.
2. **Parity test.** Same log, both sources, identical plan.
3. **Vercel.** `api/index.py`, `vercel.json`, `public/`, the build step.
4. **First-run state.** Every visitor arrives with an empty log, which is the one
   state the UI has never really been designed for: the metrics read "not yet",
   pace is blank, and the day chip says `day 1 · week 1 · 0/5 today`. A stranger
   needs a first screen that says what to do.

Steps 1 to 3 are the deployment. Step 4 is what decides whether a stranger stays.
