"""Copy the UI into public/ for Vercel to serve statically.

One source file. index.html lives at src/lcsr/static/index.html and is copied
here at build time, because two copies of a thousand-line file that drift apart
is a worse problem than a ten-line build script.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "lcsr" / "static" / "index.html"
OUT = ROOT / "public"

OUT.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, OUT / "index.html")
print(f"copied {SRC.relative_to(ROOT)} -> {(OUT / 'index.html').relative_to(ROOT)}")
