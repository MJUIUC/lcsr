"""The daily load: the curriculum's own, and your overrides of it.

The curriculum states a load for itself and `allowance()` encodes it. Some days
that load is wrong for you, so every tier can be overridden and the whole day can
be capped. Defaults are the curriculum's, so a fresh install behaves exactly as
it did before settings existed.

Kept in one module, and composed by one pure function, because the interaction
between "the curriculum says 3 foundations", "you said 1 core", "keep foundations
alive while any remain" and "no more than 4 a day" spans four rules that used to
live in three places. A wrong combination does not raise; it silently hands you
the wrong day, and the tier that goes to zero is the one that never gets worked
again. tests/test_settings.py runs the truth table.
"""

import json
from dataclasses import asdict, dataclass, replace

from . import store
from .store import LOCK, atomic_write


def _file():
    """Resolved per call, not bound at import.

    GOTCHA: a module-level `FILE = HOME / "settings.json"` captures store.HOME as
    it was when this module was first imported. Every test isolates itself by
    monkeypatching store.HOME, so a captured path silently keeps pointing at the
    real ~/.lcsr and the suite reads whatever the developer happens to have
    configured. That is not a hypothetical: it turned three unrelated plan tests
    red the first time a real settings.json existed, and it would have turned
    them GREEN just as easily.
    """
    return store.HOME / "settings.json"

# The tiers that count toward the daily total. 'custom' is deliberately absent:
# your own additions are yours, and target_today has always excluded them.
COUNTED = ("foundations", "core", "reps")

# Cut order when the total cap bites. Straight from the curriculum: "cut Reps and
# Stretch before you cut Core, and raise the number of spaced re-solves." Core is
# cut last because it is the spine of the schedule; reps are interleaving and
# survive being thinned.
CUT_ORDER = ("reps", "foundations", "core")

# A cap has to exist or a typo in the UI becomes a 10,000-problem day.
MAX_PER_TIER = 50

# Each pass after the first adds this many new problems a day, onto core. Core
# because it is the only tier present in every week, and because a second pass
# over material you have already seen is exactly when you can carry more. The
# bonus is part of the curriculum's load for the pass, so it lands BEFORE your
# overrides and before the cap: setting core yourself still wins, and a total
# cap still caps.
PASS_BONUS_PER_SPRINT = 1


# Per-day intake of NEW problems, from the load the curriculum states for itself:
# "~4-5/day in weeks 1-3 (the foundations are quick), ~3/day in weeks 4-11,
# ~3-4/day in weeks 12-16, plus the spaced re-solves." Reps start in week 3.
#
# Due re-solves are deliberately NOT counted against this. They are mandatory and
# the curriculum lists them as additional to the daily intake.
def allowance(week: int) -> dict[str, int]:
    if week <= 2:
        return {"foundations": 3, "core": 2, "reps": 0, "custom": 2}
    if week == 3:
        return {"foundations": 3, "core": 2, "reps": 1, "custom": 2}
    if week <= 11:
        return {"foundations": 0, "core": 2, "reps": 1, "custom": 2}
    return {"foundations": 0, "core": 2, "reps": 2, "custom": 2}


@dataclass(frozen=True)
class Settings:
    """None means "follow the curriculum", which is not the same as 0.

    0 is a real instruction to stop issuing that tier. Storing them as the same
    value would make "pause foundations for a week" indistinguishable from "use
    the default", and the default is nonzero in weeks 1-3.
    """
    foundations: int | None = None
    core: int | None = None
    reps: int | None = None
    daily_total: int | None = None

    def is_default(self) -> bool:
        return all(v is None for v in asdict(self).values())


def _clean(v, field: str) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):                      # True would read as 1
        raise ValueError(f"{field} must be a whole number")
    if isinstance(v, float) and not v.is_integer():
        raise ValueError(f"{field} must be a whole number")
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number") from None
    if n < 0:
        raise ValueError(f"{field} cannot be negative")
    if n > MAX_PER_TIER:
        raise ValueError(f"{field} cannot be more than {MAX_PER_TIER}")
    return n


def from_dict(d: dict) -> Settings:
    return Settings(**{k: _clean(d.get(k), k)
                       for k in ("foundations", "core", "reps", "daily_total")})


def load() -> Settings:
    """Not cached: the UI changes these mid-session and must see them at once."""
    f = _file()
    if not f.exists():
        return Settings()
    try:
        return from_dict(json.loads(f.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError, TypeError):
        # A hand-edited file that no longer parses must not take the tool down.
        # The curriculum's own load is always a safe thing to fall back to.
        return Settings()


def save(s: Settings) -> Settings:
    with LOCK:
        atomic_write(_file(), json.dumps(asdict(s), indent=1) + "\n")
    return s


def update(**kw) -> Settings:
    """Change only the fields named. Passing None for one clears that override."""
    with LOCK:
        cur = load()
        for k, v in kw.items():
            if k not in ("foundations", "core", "reps", "daily_total"):
                raise ValueError(f"unknown setting {k!r}")
            cur = replace(cur, **{k: _clean(v, k)})
        return save(cur)


def reset() -> Settings:
    return save(Settings())


def trim_to_total(q: dict[str, int], total: int) -> dict[str, int]:
    """Shrink a quota until the counted tiers fit inside `total`."""
    q = dict(q)
    over = sum(q[t] for t in COUNTED) - total
    for tier in CUT_ORDER:
        if over <= 0:
            break
        take = min(q[tier], over)
        q[tier] -= take
        over -= take
    return q


def daily_quota(week: int, foundations_remaining: int,
                s: Settings | None = None, sprint: int = 1) -> dict[str, int]:
    """The whole rule for how many new problems a day offers, in one place.

    Order matters and is the reason this is one function rather than five:

    0. the curriculum's load for that week, plus the pass bonus;
    1. (see 0);
    2. foundations stay alive while any remain, because intake_week() is derived
       from CORE progress and allowance() zeroes foundations from week 4 -- so
       finishing weeks 1-3's core would otherwise strand every remaining
       foundation. One tier's progress must not zero another's;
    3. your per-tier overrides, which beat both of the above, including the
       keep-alive: setting foundations to 0 means 0;
    4. the total cap, applied last so it caps what you will actually be handed
       rather than what the curriculum proposed.

    GOTCHA: a small enough total drives lower-priority tiers to 0 by design (that
    is what a cap is), and a tier at 0 is a tier that makes no progress that day.
    That is legitimate when asked for and a trap when arrived at by accident, so
    the settings UI shows the resulting mix rather than only the inputs.
    """
    s = s or Settings()
    q = dict(allowance(week))
    q["core"] += PASS_BONUS_PER_SPRINT * max(0, sprint - 1)

    if s.foundations is None:
        if not q["foundations"] and foundations_remaining:
            q["foundations"] = min(3, foundations_remaining)
    else:
        q["foundations"] = s.foundations
    if s.core is not None:
        q["core"] = s.core
    if s.reps is not None:
        q["reps"] = s.reps

    if s.daily_total is not None:
        q = trim_to_total(q, s.daily_total)
    return q


def describe(week: int, foundations_remaining: int, s: Settings,
             sprint: int = 1) -> dict:
    """What the settings screen needs: the inputs, the defaults, and the result."""
    base = dict(allowance(week))
    base["core"] += PASS_BONUS_PER_SPRINT * max(0, sprint - 1)
    return {
        "settings": asdict(s),
        "is_default": s.is_default(),
        "curriculum": base,
        "effective": daily_quota(week, foundations_remaining, s, sprint),
        # What the NEXT pass would hand you, computed here rather than as "+1"
        # in the page: a total cap can absorb the bonus entirely, and promising
        # an increase that will not arrive is worse than not promising one.
        "effective_next_pass": daily_quota(week, foundations_remaining, s, sprint + 1),
        "max_per_tier": MAX_PER_TIER,
        "week": week,
        "sprint": sprint,
        "pass_bonus": PASS_BONUS_PER_SPRINT * max(0, sprint - 1),
    }
