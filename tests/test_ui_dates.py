"""The UI's date arithmetic, exercised across timezones.

This guards a real bug: addDays parsed "YYYY-MM-DD" as LOCAL midnight and then
serialised with toISOString(), so in every zone at or east of Greenwich "+1 day"
returned the SAME date and the day stepper silently did nothing. It passed every
server-side test, because the defect was entirely in the browser.
"""

import json
import re
import shutil
import os
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).parent.parent / "src" / "lcsr" / "static" / "index.html"

# zones spanning UTC-11 to UTC+14, plus DST-observing ones
ZONES = ["UTC", "Asia/Kolkata", "Asia/Tokyo", "Pacific/Kiritimati",
         "Europe/London", "America/New_York", "Pacific/Midway"]

CASES = [
    ("2026-09-01", 1, "2026-09-02"),
    ("2026-09-01", -1, "2026-08-31"),
    ("2026-12-31", 1, "2027-01-01"),   # year boundary
    ("2026-01-01", -1, "2025-12-31"),
    ("2026-02-28", 1, "2026-03-01"),   # non-leap February
    ("2028-02-28", 1, "2028-02-29"),   # leap February
    ("2026-03-08", 1, "2026-03-09"),   # US DST spring-forward
    ("2026-11-01", 1, "2026-11-02"),   # US DST fall-back
]

# GOTCHA: the guard and the call must agree about where node is. This used to
# skip on `shutil.which("node")`, which searches the real PATH, and then run with
# a hardcoded PATH of "/usr/bin:/bin:/opt/homebrew/bin". On any machine where node
# lives somewhere else -- a CI runner, nvm, a Linux distro -- the guard found it,
# the test therefore did NOT skip, and the subprocess then died with
# FileNotFoundError. Resolve once, use that absolute path.
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None,
                                reason="node not available to run the UI's JS")


def extract(name: str) -> str:
    src = HTML.read_text(encoding="utf-8")
    m = re.search(rf"function {name}\(.*?\)\{{[\s\S]*?\n\}}", src)
    assert m, f"{name}() not found in index.html"
    return m.group(0)


@pytest.mark.parametrize("tz", ZONES)
def test_add_days_is_timezone_independent(tz):
    script = extract("addDays") + f"""
const cases = {json.dumps(CASES)};
console.log(JSON.stringify(cases.map(([iso, n]) => addDays(iso, n))));
"""
    # Inherit the environment so node keeps whatever it needs to start; only TZ
    # is overridden, which is the one variable this test is actually about.
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                         env={**os.environ, "TZ": tz})
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got == [want for _, _, want in CASES], f"in {tz}"
