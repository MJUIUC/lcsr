# leetcode-srs

Spaced repetition for LeetCode-style problems, built on the strongest available
evidence rather than on the folk version of "Anki for LeetCode".

**Status: design phase. No implementation yet.**

Start here:

- [`docs/evidence.md`](docs/evidence.md) — what the literature actually supports,
  including where it *fails* to support the obvious design.
- [`docs/design.md`](docs/design.md) — the system that follows from that evidence.

The one-line summary of why this is not a flashcard app: the evidence for
retrieval practice on **procedural** skill is weak-to-null, while the evidence
for **interleaving**, **varied practice**, and **worked examples** on problem
solving is strong. So the scheduled unit here is a *pattern*, the retrieval item
is a *fresh problem* you have not seen, and what gets graded first is whether you
**recognised** the pattern — not whether you eventually typed a passing solution.
