"""Vercel entrypoint.

The same request handler the local server uses, with STATELESS on. That flag is
the whole difference: there is no writable disk here, so the browser holds the
log, the custom problems and the settings, posts them with every request, and
gets back the records to persist. Nothing derived is stored server-side, and
nothing is shared between visitors.

GOTCHA: do not point Vercel at `lcsr.server:Handler` directly. It builds and it
serves, and every write then targets ~/.lcsr on a read-only filesystem: logging
fails and every read comes back empty, with the UI looking perfectly fine.
"""

import sys
from pathlib import Path

# The package is not installed in the function image; it is included as source.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lcsr.server import Handler as _Handler  # noqa: E402


class handler(_Handler):                     # Vercel looks for this name
    STATELESS = True
