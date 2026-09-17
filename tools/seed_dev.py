"""Seed ~/.lcsr-dev with realistic log entries for development.

Run this once before starting a dev session:

    python tools/seed_dev.py

It populates ~/.lcsr-dev/log.jsonl with a spread of solved and stuck
attempts across several weeks, so every part of the UI has something
to render:

  - Problems in various states (new, learning/due, done)
  - Stuck attempts with mistake classes and markdown notes
  - Solved attempts with approach notes
  - A mix of recent and older dates so Progress shows multiple days
  - One re-solve sequence (stuck → stuck → solved) to show the ladder

Run with --reset to wipe and re-seed from scratch.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Point at dev home before importing anything from the package.
DEV_HOME = Path.home() / ".lcsr-dev"
DEV_HOME.mkdir(parents=True, exist_ok=True)
os.environ["LCSR_HOME"] = str(DEV_HOME)

# Now safe to import store.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lcsr.store import LOG, make_entry, MISTAKES
from lcsr.schedule import SOLVED, STUCK


def entry(pid, outcome, days_ago, mistake=None, approach_min=None, note=None):
    on = date.today() - timedelta(days=days_ago)
    e = make_entry(pid, outcome, on, mistake, approach_min, note)
    # Back-date the timestamp to match the attempt date for realism.
    ts = datetime.combine(on, datetime.now().time()).astimezone()
    e["ts"] = ts.isoformat(timespec="seconds")
    return e


SEED_ENTRIES = [
    # ── W0 foundations: mix of solved and untouched ──────────────────────────
    entry(1,   SOLVED, 14, approach_min=8.2,
          note="## Two Sum\n\nUsed a hashmap to store complements.\n\n```python\ndef twoSum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i\n```\n\nKey insight: one pass, complement lookup is O(1)."),
    entry(217, SOLVED, 13, approach_min=5.1,
          note="Set membership check. Sorted would also work but O(n log n)."),
    entry(242, SOLVED, 13, approach_min=6.4),
    entry(49,  STUCK,  12, mistake="no-pattern", approach_min=22.0,
          note="Forgot that sorted string is a valid hashmap key. Tried counting chars instead which works but is slower to implement."),
    entry(49,  STUCK,  9,  mistake="invariant", approach_min=18.5,
          note="Got the grouping right but returned a list of lists instead of list of values. Off-by-one on the dict structure."),
    entry(49,  SOLVED, 6,  approach_min=4.2,
          note="Finally clicked. `tuple(sorted(s))` as key, defaultdict(list) for groups."),

    # ── W1 fixed window ──────────────────────────────────────────────────────
    entry(643, SOLVED, 11, approach_min=7.8,
          note="## Max Average Subarray\n\nSlide a window of size k:\n\n```python\nwindow = sum(nums[:k])\nbest = window\nfor i in range(k, len(nums)):\n    window += nums[i] - nums[i-k]\n    best = max(best, window)\nreturn best / k\n```"),
    entry(1456, SOLVED, 10, approach_min=9.1),
    entry(1052, STUCK,  8,  mistake="edge-case", approach_min=24.5,
          note="Missed that the grumpy window adds to existing satisfaction, not replaces it. Classic off-by-one in what the window contributes."),
    entry(167, SOLVED, 7,  approach_min=6.3,
          note="Two pointers from both ends since array is sorted. Move left up if sum too small, right down if too large."),
    entry(11,  STUCK,  5,  mistake="invariant", approach_min=21.0,
          note="Kept second-guessing which pointer to move. The rule: always move the shorter side because moving the taller one can only decrease the area."),

    # ── W2 variable window ───────────────────────────────────────────────────
    entry(209, SOLVED, 4,  approach_min=11.2,
          note="Shrink from left while window sum >= target. Track minimum length seen."),
    entry(3,   SOLVED, 3,  approach_min=8.7,
          note="## Longest Substring Without Repeating\n\nSliding window with a set:\n- Expand right, add to set\n- When duplicate found, shrink left until removed\n\n```python\nleft = 0\nseen = set()\nbest = 0\nfor right, c in enumerate(s):\n    while c in seen:\n        seen.remove(s[left])\n        left += 1\n    seen.add(c)\n    best = max(best, right - left + 1)\n```"),
    entry(1004, STUCK, 2,  mistake="off-by-one", approach_min=19.3,
          note="Shrink condition was wrong. Should shrink when zeros in window > k, not >= k."),

    # ── W3 prefix sum (due for re-solve) ─────────────────────────────────────
    entry(560, STUCK,  32, mistake="no-pattern", approach_min=25.0,
          note="Did not recognise prefix sum pattern. Tried sliding window but negatives broke it."),
    entry(560, STUCK,  22, mistake="invariant", approach_min=18.0,
          note="Got the prefix sum idea but forgot to initialise `counts[0] = 1` for subarrays starting at index 0."),
    # 560 is now due for re-solve (30 days after second stuck)

    # ── W5 monotonic stack (recent, due today) ───────────────────────────────
    entry(739, STUCK,  3,  mistake="no-pattern", approach_min=23.1,
          note="Tried brute force O(n²). Did not recognise monotonic stack pattern from 'next greater element'."),
    # 739 returns in 3 days from 3 days ago = due today

    # ── W6 binary search ─────────────────────────────────────────────────────
    entry(875, SOLVED, 1,  approach_min=13.4,
          note="## Koko Eating Bananas\n\nBinary search on the answer (speed k).\n\nFeasibility check: can Koko finish all piles in h hours at speed k?\n\n```python\ndef feasible(k):\n    return sum(math.ceil(p/k) for p in piles) <= h\n\nlo, hi = 1, max(piles)\nwhile lo < hi:\n    mid = (lo + hi) // 2\n    if feasible(mid): hi = mid\n    else: lo = mid + 1\nreturn lo\n```\n\nKey: answer is monotone — if k works, anything larger also works."),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true",
                    help="wipe ~/.lcsr-dev/log.jsonl before seeding")
    a = ap.parse_args()

    if a.reset and LOG.exists():
        LOG.unlink()
        print(f"cleared {LOG}")

    if LOG.exists():
        existing = sum(1 for line in LOG.read_text().splitlines() if line.strip())
        print(f"{LOG} already has {existing} entries.")
        print("Run with --reset to wipe and re-seed.")
        return

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as f:
        for e in SEED_ENTRIES:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"seeded {len(SEED_ENTRIES)} entries into {LOG}")
    print()
    print("Dev environment ready. Launch with:")
    print("  bash dev.sh")
    print("  # or: .venv/bin/lcsr app --dev --debug")


if __name__ == "__main__":
    main()
