"""The whole scheduler. Kept pure and alone on purpose.

The curriculum's rule: a failed problem returns at +3d, +10d, +30d; a problem
solved cold does not return at all. `box` is the position in that ladder.

GOTCHA: a wrong cell in this table is invisible in code review and does not
raise — it silently shifts every future due date and quietly corrupts the
30-day cold re-solve rate, which is the one metric the curriculum says predicts
interview performance. Hence the exhaustive test in tests/test_schedule.py over
all 8 (box, outcome) pairs. Change a cell here and that test must change too,
deliberately.
"""

from dataclasses import dataclass

SOLVED = "solved"
STUCK = "stuck"
OUTCOMES = (SOLVED, STUCK)

# box -> days until the re-solve that leaving this box schedules
LADDER = {0: 3, 1: 10, 2: 30}


@dataclass(frozen=True)
class Next:
    """Where a problem lands after an attempt.

    box is None and due_in_days is None once the problem is finished.
    """
    done: bool
    box: int | None
    due_in_days: int | None


def advance(box: int | None, outcome: str) -> Next:
    """Fold one attempt into a problem's schedule state.

    box is None before the first failure (i.e. the problem has never entered the
    ladder). Failing at any position resets to the bottom: the point of +3/+10/+30
    is to re-earn the spacing, not to resume it.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}, expected one of {OUTCOMES}")

    if outcome == STUCK:
        return Next(done=False, box=0, due_in_days=LADDER[0])

    if box is None:
        return Next(done=True, box=None, due_in_days=None)  # solved cold, first try

    if box >= max(LADDER):
        return Next(done=True, box=None, due_in_days=None)  # cleared the ladder

    return Next(done=False, box=box + 1, due_in_days=LADDER[box + 1])
