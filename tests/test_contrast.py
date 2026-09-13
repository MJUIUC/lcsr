"""WCAG contrast, computed from the stylesheet rather than eyeballed.

Contrast is the one design property that is objectively checkable and completely
invisible in review: #7c7c85 hint text on white looks fine to someone with good
eyesight on a good monitor and is 4.1:1, which fails. Both themes get checked,
because a palette that passes in dark routinely fails in light and the reverse.

Thresholds are WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text and for
non-text UI (borders that carry meaning, focus rings, the nav underline).

GOTCHA: the pairs below are written by hand and the stylesheet is not. If you
restyle an element to use a different token, this file does not follow you, and
a passing run then proves nothing about the thing you changed. Add the pair.
"""

import pathlib
import re

import pytest

from _html import tag_blocks

HTML = pathlib.Path(__file__).resolve().parent.parent / "src" / "lcsr" / "static" / "index.html"
CSS = tag_blocks(HTML.read_text(encoding="utf-8"), "style")[0]

BODY, LARGE = 4.5, 3.0


def _tokens(selector: str) -> dict[str, str]:
    block = re.search(re.escape(selector) + r"\{(.*?)\}", CSS, re.S)
    assert block, f"{selector} not found in the stylesheet"
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", block.group(1)))


LIGHT = _tokens(":root")
# Dark overrides light rather than replacing it: a token the dark block does not
# mention (--brand) genuinely inherits the :root value, so resolving the dark
# palette means overlaying, not reading the dark block alone.
DARK = {**LIGHT, **_tokens(":root[data-theme=dark]")}
SYSTEM_DARK = _tokens(":root:not([data-theme=light])")


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(h: str) -> float:
    def chan(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = map(chan, _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# (what it is, foreground, background, minimum). A literal hex is used where the
# stylesheet uses one; everything else is a token resolved per theme.
PAIRS = [
    ("body text on the page background",   "--ink",    "--bg",          BODY),
    ("body text on a panel",               "--ink",    "--panel",       BODY),
    ("secondary text on a panel",          "--mid",    "--panel",       BODY),
    ("secondary text on an inset panel",   "--mid",    "--panel2",      BODY),
    ("hint text on a panel",               "--muted",  "--panel",       BODY),
    ("hint text on an inset panel",        "--muted",  "--panel2",      BODY),
    ("hint text on the page background",   "--muted",  "--bg",          BODY),
    ("accent text on a panel",             "--accent", "--panel",       BODY),
    ("accent text on the background",      "--accent", "--bg",          BODY),
    ("accent text on its own tint",        "--accent", "--accent-soft", BODY),
    ("warning text on a panel",            "--warn",   "--panel",       BODY),
    ("warning text on its own tint",       "--warn",   "--warn-soft",   BODY),
    ("danger text on a panel",             "--danger", "--panel",       BODY),
    ("success text on a panel",            "--ok",     "--panel",       BODY),
    ("Easy badge",                         "--easy",   "--panel",       BODY),
    ("Medium badge",                       "--medium", "--panel",       BODY),
    ("Hard badge",                         "--hard",   "--panel",       BODY),
    ("pool accent on a panel",             "--pool",   "--panel",       BODY),
    ("pool accent on its own tint",        "--pool",   "--pool-soft",   BODY),
    # .evid sits on --panel2 and its link paints --accent.
    ("evidence note text",                 "--muted",  "--panel2",      BODY),
    ("evidence note link",                 "--accent", "--panel2",      BODY),
    # The success toast is a solid pill; its Undo button must read as a control,
    # so it is checked against the pill at the 3:1 non-text threshold too.
    ("toast message",                      "--toast-ink", "--toast-bg",     BODY),
    ("toast undo label",                   "--toast-btn-ink", "--toast-btn", BODY),
    ("toast undo against the pill",        "--toast-btn", "--toast-bg",      LARGE),
    ("premium (gold) badge",               "--gold",   "--panel",       BODY),
    # .btn.primary paints --brand and sets this literal ink on it.
    ("primary button label on the brand",  "#1a1200",  "--brand",       BODY),
    # .badge.nmax and .pool .btn.primary use color:var(--panel) on the pool
    # accent, so the ink tracks the theme: dark on light violet, light on dark.
    ("max-overlap badge label",            "--panel",  "--pool",        BODY),
    ("pool primary button label",          "--panel",  "--pool",        BODY),
    # Non-text and large-text uses of the accent: the wordmark, the active nav
    # underline, and the progress-bar fills all paint --accent, never --brand.
    ("wordmark and nav underline",         "--accent", "--bg",          LARGE),
    ("progress fill against its track",    "--accent", "--line",        LARGE),
]


@pytest.mark.parametrize("theme_name,theme", [("light", LIGHT), ("dark", DARK)])
@pytest.mark.parametrize("label,fg,bg,need", PAIRS)
def test_contrast(theme_name, theme, label, fg, bg, need):
    f, b = theme.get(fg, fg), theme.get(bg, bg)
    got = ratio(f, b)
    assert got >= need, (
        f"{theme_name}: {label} is {got:.2f}:1 ({f} on {b}), needs {need}:1"
    )


def test_the_two_dark_palettes_are_identical():
    """The dark palette is written twice: once under the prefers-color-scheme
    media query, once under [data-theme=dark] so the toggle can win. If they
    drift, someone on a dark OS and someone who pressed Dark see different
    colours, and only one of the two gets contrast-checked."""
    assert SYSTEM_DARK == _tokens(":root[data-theme=dark]"), \
        set(SYSTEM_DARK.items()) ^ set(_tokens(":root[data-theme=dark]").items())


def test_the_brand_orange_is_never_used_as_ink():
    """#ffa116 is 1.84:1 on the light background.

    It is a fill colour with dark text on it, never text or a border. --accent is
    the text-safe variant and resolves to #ffa116 in dark anyway, so the
    LeetCode orange is not lost; it is just not load-bearing where it cannot be.
    """
    flat = CSS.replace(" ", "")
    # (?<![-a-z]) so border-COLOR:var(--brand) does not read as color:var(--brand)
    hits = re.findall(r"(?<![-a-z])(color|border-bottom-color):var\(--brand\)", flat)
    assert not hits, hits
