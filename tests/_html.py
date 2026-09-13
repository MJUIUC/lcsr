"""Pull the raw contents of <script> / <style> blocks out of the page.

A parser, not a regex. The regex this replaces (r"<script>(.*?)</script>") is
CodeQL's py/bad-tag-filter: it misses <SCRIPT>, a tag with attributes, and
`</script >`. Here it only reads our own index.html, so nothing was exploitable,
but the same blindness meant a harmless edit like `<script defer>` would have made
these tests silently extract the wrong block, or nothing, and keep passing.

html.parser treats script and style as raw-text elements, so a `</div>` inside a
JavaScript template string does not end the block; only the real closing tag does.
"""

from html.parser import HTMLParser


class _Blocks(HTMLParser):
    def __init__(self, tag: str):
        super().__init__(convert_charrefs=False)
        self.tag, self.blocks, self._buf = tag, [], None

    def handle_starttag(self, tag, attrs):
        if tag == self.tag:            # tag names arrive lower-cased
            self._buf = []

    def handle_endtag(self, tag):
        if tag == self.tag and self._buf is not None:
            self.blocks.append("".join(self._buf))
            self._buf = None

    def handle_data(self, data):       # may arrive in several chunks
        if self._buf is not None:
            self._buf.append(data)


def tag_blocks(html: str, tag: str) -> list[str]:
    """Every <tag> block's raw contents, in document order."""
    p = _Blocks(tag.lower())
    p.feed(html)
    p.close()
    return p.blocks
