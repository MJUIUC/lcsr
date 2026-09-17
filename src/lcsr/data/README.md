# lcsr data files

Static reference data bundled with the package. Everything here is
read-only at runtime — the only files that change on a user's machine
are in `~/.lcsr/` (log, settings, prefs, problem description cache).

---

## problems.json

**314 problems extracted from the 18-week DSA curriculum PDF.**

Each entry is one LeetCode problem in curriculum order:

| Field | Type | Description |
|---|---|---|
| `id` | int | LeetCode problem number |
| `title` | string | Problem title |
| `hard` | bool | Whether LeetCode classifies it as Hard |
| `tier` | string | `"foundations"`, `"core"`, or `"reps"` — controls daily scheduling |
| `week` | int\|null | Curriculum week (1–18); null for stretch/consolidation problems |
| `block` | string | Pattern group name (e.g. `"Variable window"`) |
| `role` | string | Same as tier, used internally |
| `order` | float | Sort position within the curriculum; fractional values slot added problems between existing ones without renumbering |
| `immediately_after_prev` | bool | True if the curriculum says to solve this immediately after the previous problem |

`cue` is absent from this file — see `problems_extra.json` for the 10 problems that have one.

Generated from the PDF by `tools/parse_curriculum.py`. **Do not hand-edit** — changes will be overwritten on regeneration. To add or modify problems, use `problems_extra.json` or the `lcsr add` CLI command.

---

## problems_extra.json

**10 problems added by this project to fill curriculum gaps.**

Same schema as `problems.json` plus two additional fields:

| Field | Type | Description |
|---|---|---|
| `cue` | string\|null | Recognition hint for the student (see cues below) |
| `url` | string\|null | Override URL; null means the standard LeetCode URL is derived from the slug |

These are problems the original curriculum taught in the wrong order (hard variant before base exemplar). They are slotted into their correct position using fractional `order` values.

Loaded after `problems.json`; a matching `id` in this file wins, which is how a problem can be re-tagged or re-ordered without touching the generated file.

---

## slugs.json

**Map of LeetCode problem ID → URL slug.**

```json
{ "1": "two-sum", "2": "add-two-numbers", ... }
```

Used by `curriculum.url_of(id)` to construct `https://leetcode.com/problems/<slug>/`. Covers all 324 problems (314 curriculum + 10 extra).

Generated alongside `problems.json`. Do not hand-edit.

---

## cues.json

**20 cue-to-pattern rows from the curriculum PDF.**

The curriculum's own "cue table" — the object of study the student is supposed to reconstruct from memory. Each entry is a recognition phrase mapped to the algorithm to reach for:

| Field | Type | Description |
|---|---|---|
| `group` | string | Section heading (always `"From the curriculum"` for this file) |
| `says` | string | What the problem statement says that should trigger recognition |
| `reach_for` | string | The algorithm or data structure to apply |
| `because` | string | Why this pattern is correct; often contrasts with the wrong approach |
| `problems` | int[] | 2–3 problem IDs from the curriculum that best exemplify this cue |

Generated from the PDF by `tools/parse_curriculum.py`. Do not hand-edit — use `cues_extra.json` for additions.

---

## cues_extra.json

**24 additional cue entries that contrast confusable patterns.**

Same schema as `cues.json`. These entries were added by this project to help students distinguish patterns that are easy to mix up (e.g. fixed window vs variable window vs prefix sum, DP vs greedy, BFS vs Dijkstra).

Unlike `cues.json`, these are hand-written and safe to edit. The `because` field is mandatory for every entry here — the whole point of these additions is to explain the discrimination, not just name the pattern.

Loaded after `cues.json` and concatenated into a single list of 44 entries (indices 0–43) used by `curriculum.cues()`.

---

## cue_map.json

**Source of truth mapping every curriculum problem ID to one or more cue indices.**

```json
{
  "1":   [2],
  "239": [5, 25],
  "322": [16, 30],
  ...
}
```

Keys are problem IDs as strings. Values are arrays of integer cue indices (0-based, indexing into the concatenated list produced by `curriculum.cues()` — that is, `cues.json` entries first at indices 0–19, then `cues_extra.json` entries at indices 20–43).

Multi-index entries (e.g. `[5, 25]`) mean the problem genuinely exercises two distinct patterns. The first index is used as the primary navigation target when linking from a problem card to the Cue table.

313 of 314 problems are mapped. The one unmapped problem (273, Integer to English Words) maps to index 43 (Recursive decomposition). All 314 are covered.

**This file is hand-maintained.** It is the join between the problem list and the cue table that the JSON data does not otherwise express. When adding a new problem via `lcsr add`, add its mapping here too.

### Cue index quick reference

| Index | reach_for |
|---|---|
| 0 | Fixed window |
| 1 | Variable window, shrink while invalid |
| 2 | Prefix sum + hashmap |
| 3 | atMost(K) − atMost(K−1) |
| 4 | Monotonic stack |
| 5 | Monotonic deque |
| 6 | Binary search on the answer + feasibility check |
| 7 | Heap: one, or two facing each other |
| 8 | Sort by start (merge) or by end (greedy count) |
| 9 | DFS returning one value, side variable tracking another |
| 10 | BFS: multi-source if there are several origins |
| 11 | Dijkstra: unless a hop limit is imposed |
| 12 | Union-find |
| 13 | Topological sort (Kahn's) |
| 14 | It is still a graph: search over generated neighbours |
| 15 | Backtracking; sort first if duplicates exist |
| 16 | DP: define the state before writing anything |
| 17 | 2-D DP table |
| 18 | Trie |
| 19 | XOR |
| 20 | Two pointers from both ends (sorted array) |
| 21 | Fixed window (extra group) |
| 22 | Variable window, shrink while invalid (extra group) |
| 23 | Prefix sum + hashmap (extra group) |
| 24 | atMost(K) − atMost(K−1) (extra group) |
| 25 | Monotonic deque, not a heap (extra group) |
| 26 | Two pointers in the same direction (slow write / fast read) |
| 27 | Greedy (local choice is safe) |
| 28 | DP: state must carry whatever the choice affects |
| 29 | DP, never greedy (counting) |
| 30 | DP over the target (arbitrary denominations) |
| 31 | Greedy, sorting by END (non-overlapping intervals) |
| 32 | DP as a state machine (cooldown / k transactions) |
| 33 | Backtracking (return ALL objects) |
| 34 | DP (return count or best) |
| 35 | BFS: multi-source (extra group) |
| 36 | Bellman–Ford / DP over hop count |
| 37 | Binary search on the answer (extra group) |
| 38 | Heap of size k (stream / top-k) |
| 39 | Trie (extra group) |
| 40 | Union-find (extra group) |
| 41 | Use the index as the hash |
| 42 | Halve the exponent (fast exponentiation) |
| 43 | Recursive decomposition |

---

## frequent.json

**390 problems merged from five public interview lists.**

Used by the Interview Pool feature (currently removed from the desktop app UI but retained for potential future use).

```json
{
  "labels": {
    "top150": "Top Interview 150",
    "lc75":   "LeetCode 75",
    "top100": "Top 100 Liked",
    "striver": "Striver A2Z",
    "neetcode150": "NeetCode 150"
  },
  "problems": [
    { "id": 1, "title": "Two Sum", "slug": "two-sum",
      "lists": ["top150", "lc75", ...], "difficulty": "Easy",
      "paid": false, "count": 3 },
    ...
  ]
}
```

`count` is the number of lists a problem appears on — used for weighted random draw (problems on more lists are drawn more frequently). Generated by `tools/build_frequent.py`. Do not hand-edit.
