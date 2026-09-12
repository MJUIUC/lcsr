"""The tab wiring, checked statically.

There is no DOM here, so this checks the one thing that broke without any test
noticing: the lists that have to agree about what a tab is. A tab needs an entry
in TABS, a view function in the render map, and its data fetched before it can
render. Those were three separate lists, and adding Settings to two of the three
left the page dead on reload with an error that blamed the server.
"""

import pathlib
import re

HTML = pathlib.Path(__file__).resolve().parent.parent / "src" / "lcsr" / "static" / "index.html"
JS = re.findall(r"<script>(.*?)</script>", HTML.read_text(encoding="utf-8"), re.S)[-1]


def _block(start: str) -> str:
    """The brace-balanced body that follows `start`."""
    i = JS.index(start) + len(start)
    i = JS.index("{", i)
    depth, j = 0, i
    while j < len(JS):
        if JS[j] == "{":
            depth += 1
        elif JS[j] == "}":
            depth -= 1
            if depth == 0:
                return JS[i:j + 1]
        j += 1
    raise AssertionError(f"unbalanced braces after {start!r}")


TAB_KEYS = set(re.findall(r"\{k:'(\w+)',", JS[JS.index("const TABS"):JS.index("];", JS.index("const TABS"))]))
VIEW_MAP = dict(re.findall(r"(\w+):(v[A-Z]\w+)", _block("function render(opts={})")))


def test_every_tab_has_a_view():
    assert TAB_KEYS == set(VIEW_MAP), TAB_KEYS ^ set(VIEW_MAP)


def test_every_view_in_the_map_is_actually_defined():
    for tab, fn in VIEW_MAP.items():
        assert f"function {fn}(" in JS, f"{tab} maps to {fn}, which does not exist"


def test_only_ensure_data_decides_what_a_tab_fetches():
    """The bug: go() and the bootstrap each had their own copy of this list.

    Settings was added to go()'s copy only, so opening the tab worked and
    reloading on it threw before first paint. Both callers must delegate.
    """
    boot = _block("(async ()=>")
    assert "ensureData(tab)" in boot, "the bootstrap does not use ensureData"
    assert "ensureData(t)" in _block("async function go(t)"), "go() does not use ensureData"
    # No per-tab branching anywhere but ensureData.
    for caller, body in (("bootstrap", boot), ("go()", _block("async function go(t)"))):
        strays = re.findall(r"(?:tab|t)==='(\w+)'", body)
        assert not strays, f"{caller} still decides per tab: {strays}"


def test_ensure_data_only_names_real_tabs():
    named = set(re.findall(r"t==='(\w+)'", _block("async function ensureData(t)")))
    assert named <= TAB_KEYS, named - TAB_KEYS


def test_every_tab_that_needs_data_gets_it():
    """'today' is the only tab that needs nothing of its own: plan and curric are
    fetched unconditionally by the bootstrap. Every other tab reads a global that
    starts null, so it must appear in ensureData or it renders against null."""
    named = set(re.findall(r"t==='(\w+)'", _block("async function ensureData(t)")))
    assert TAB_KEYS - named == {"today"}, TAB_KEYS - named - {"today"}


def test_legacy_hashes_still_resolve_to_real_tabs():
    """Renamed tabs keep working from an old bookmark, and the target must exist."""
    for old, new in re.findall(r"tab === '(\w+)'.*?tab = '(\w+)'", JS):
        assert new in TAB_KEYS, f"#{old} redirects to #{new}, which is not a tab"
        assert old not in TAB_KEYS, f"#{old} redirects but is still a live tab"
