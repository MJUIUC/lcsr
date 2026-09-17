"""Problem description cache.

Fetches problem content from LeetCode's GraphQL API on first expand and
stores it in ~/.lcsr/problem_cache.json. The curriculum is a fixed set,
so each problem is fetched at most once. Custom problems added later are
fetched the same way on first expand.

No auth required for problem content -- only submission history needs a
session cookie. LeetCode does require a Referer header to avoid 403s.
"""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from .store import HOME, atomic_write

CACHE_FILE = HOME / "problem_cache.json"

GRAPHQL_URL = "https://leetcode.com/graphql"

QUERY = """
query questionContent($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    content
  }
}
"""


def _load() -> dict:
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save(cache: dict) -> None:
    atomic_write(CACHE_FILE, json.dumps(cache, ensure_ascii=False))


def slug_from_url(url: str) -> str:
    """Extract the title slug from a LeetCode problem URL.

    'https://leetcode.com/problems/two-sum/' -> 'two-sum'
    """
    parts = [p for p in url.rstrip("/").split("/") if p]
    # slug is the segment after 'problems'
    try:
        return parts[parts.index("problems") + 1]
    except (ValueError, IndexError):
        return ""


def _statement_only(html: str) -> str:
    """Return just the problem statement, stripping examples and constraints.

    LeetCode content is HTML. Everything before the first
    <strong>Example or <p><strong>Constraints appears to be the
    statement. We return that slice as-is so the UI can render it.
    """
    # Find the earliest of: Example heading, Constraints heading, <ul> block
    cutoffs = []
    for pattern in (
        r'<p><strong[^>]*>Example',
        r'<p><strong[^>]*>Constraint',
        r'<ul>',
    ):
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            cutoffs.append(m.start())
    if cutoffs:
        html = html[:min(cutoffs)]
    return html.strip()


def fetch(problem_id: int, url: str) -> str:
    """Return the cached problem statement HTML, fetching if necessary.

    Returns an empty string on any network or parse failure -- the UI
    should degrade gracefully rather than showing an error in the card.
    """
    cache = _load()
    key = str(problem_id)
    if key in cache:
        return cache[key]

    slug = slug_from_url(url)
    if not slug:
        return ""

    try:
        payload = json.dumps({"query": QUERY, "variables": {"titleSlug": slug}})
        req = Request(
            GRAPHQL_URL,
            data=payload.encode(),
            headers={
                "Content-Type": "application/json",
                "Referer": f"https://leetcode.com/problems/{slug}/",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        with urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode())
        content = (body.get("data") or {}).get("question") or {}
        html = content.get("content") or ""
        statement = _statement_only(html) if html else ""
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return ""

    if statement:
        cache[key] = statement
        _save(cache)

    return statement
