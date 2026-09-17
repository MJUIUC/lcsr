"""User preferences for the desktop app.

Stored in ~/.lcsr/prefs.json. Separate from settings.py, which owns
the curriculum load (server-facing). Prefs are purely local UI state
that the server never sees: timer length, and anything similar added
later (window size, etc.).

Intentionally simple: one read, one write, no migrations needed for a
flat dict of scalars.
"""

import json

from .store import HOME, atomic_write

PREFS_FILE = HOME / "prefs.json"

DEFAULTS: dict = {
    "timer_min": 25,
}


def load() -> dict:
    """Return current prefs merged onto defaults. Never raises."""
    try:
        raw = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {**DEFAULTS, **raw}
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return dict(DEFAULTS)


def save(prefs: dict) -> dict:
    """Persist prefs dict. Only known keys are written; unknown keys are dropped."""
    clean = {k: prefs[k] for k in DEFAULTS if k in prefs}
    atomic_write(PREFS_FILE, json.dumps(clean, indent=2))
    return clean


def get(key: str):
    """Read a single key."""
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value) -> dict:  # noqa: A001
    """Write a single key and return the full updated prefs."""
    if key not in DEFAULTS:
        raise ValueError(f"unknown pref {key!r}")
    p = load()
    p[key] = value
    return save(p)
