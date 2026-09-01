"""Extract the 314 problems and the cue table from the curriculum PDF.

Usage:  python tools/parse_curriculum.py [path/to/DSA-Curriculum-18-Week.pdf]

Writes src/lcsr/data/{problems,cues}.json and asserts the tier counts match the
figures the document states for itself -- if a future edition of the PDF shifts
the layout, that assertion is what tells you, rather than a silently short list.
"""

import json, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'src' / 'lcsr' / 'data'
PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / 'Desktop' / 'DSA-Curriculum-18-Week.pdf'

if not PDF.exists():
    raise SystemExit(f'PDF not found: {PDF}')

with tempfile.NamedTemporaryFile(suffix='.txt') as tmp:
    # -layout preserves the column spacing that entry parsing relies on
    subprocess.run(['pdftotext', '-layout', str(PDF), tmp.name], check=True)
    lines = Path(tmp.name).read_text(encoding='utf-8').split('\n')

# A trailing '→' means "solve immediately after the previous problem", but the
# arrow can wrap to the end of the prior line while its problem sits on the next
# one (W13: '322 Coin Change  →' / '518 Coin Change II'). Re-attach it, or the
# ordering link is silently dropped and 518 looks free-standing.
for _n, _ln in enumerate(lines):
    if _ln.rstrip().endswith('→'):
        lines[_n] = _ln.rstrip()[:-1].rstrip()
        for _m in range(_n + 1, len(lines)):
            if lines[_m].strip():
                lines[_m] = '→ ' + lines[_m].lstrip()
                break

ENTRY = re.compile(r'^(?:(→)\s*)?(\d+)\s+(.+)$')

def parse_entries(chunk):
    """Entries sit on one line separated by 2+ spaces. First int is the LC id;
    a trailing bare 'H' is the hard marker (e.g. '456 132 Pattern' -> id 456)."""
    out = []
    for line in chunk:
        for tok in re.split(r'\s{2,}', line.strip()):
            tok = tok.strip()
            if not tok:
                continue
            m = ENTRY.match(tok)
            if not m:
                print(f'UNPARSED: {tok!r}', file=sys.stderr)
                continue
            arrow, pid, title = m.group(1), int(m.group(2)), m.group(3).strip()
            hard = False
            # superscript H is glued to the last word; no LC title ends in capital H
            if len(title) > 1 and title[-1] == 'H' and title[-2] != ' ':
                hard, title = True, title[:-1].strip()
            out.append({'id': pid, 'title': title, 'hard': hard,
                        'immediately_after_prev': bool(arrow)})
    return out

problems, seen_order = [], []

# ---- Tier 0: foundations (lines 85..111), subheadings are non-entry lines
i = 84
group = None
while i < 111:
    ln = lines[i]
    if ln.strip() and not ENTRY.match(re.split(r'\s{2,}', ln.strip())[0]):
        group = ln.strip()
    elif ln.strip():
        for e in parse_entries([ln]):
            e.update(tier='foundations', week=0, block=group, role='foundation')
            problems.append(e)
    i += 1

# ---- Weeks 1..16
week_hdr = re.compile(r'^\s*W(\d+)\s{2,}(.+)$')
bounds = [(n, week_hdr.match(lines[n])) for n in range(len(lines)) if week_hdr.match(lines[n])]
bounds = [(n, int(m.group(1)), m.group(2).strip()) for n, m in bounds]
for idx, (start, wk, title) in enumerate(bounds):
    end = bounds[idx + 1][0] if idx + 1 < len(bounds) else 377
    cue, role, buf = None, None, []
    def flush():
        for e in parse_entries(buf):
            e.update(tier='core' if role == 'core' else 'reps', week=wk,
                     block=title, cue=cue, role=role)
            problems.append(e)
    for ln in lines[start + 1:end]:
        s = ln.strip()
        if s.startswith('Cue:'):
            cue = s[4:].strip(); continue
        if s == 'CORE':
            flush(); buf, role = [], 'core'; continue
        if s.startswith('REPS'):
            flush(); buf, role = [], 'reps'; continue
        # Commentary paragraphs are indented 2+ spaces; entry lines are flush-left.
        # This matters: 7 commentary lines OPEN with a problem number ("560 and
        # last week's 209 read almost identically..."), so matching on a leading
        # integer silently admits them and inflates the reps count from 113 to 120.
        if not s or re.match(r'^\s{2,}', ln):
            continue
        if role:
            buf.append(ln)
    flush()

# ---- Tier 3: stretch
for e in parse_entries(lines[388:399]):
    e.update(tier='stretch', week=None, block='Stretch', role='stretch')
    problems.append(e)

# Document order is load-bearing: the curriculum says the core is "never skipped,
# never reordered" and several blocks say "solve in the listed order", so the
# position in the PDF has to survive extraction. Dict key order is not enough --
# anything that round-trips through JSON and back can lose it.
for _i, _p in enumerate(problems):
    _p['order'] = _i

counts = {}
for p in problems:
    counts[p['tier']] = counts.get(p['tier'], 0) + 1
print('counts:', counts, 'total:', len(problems))
ids = [p['id'] for p in problems]
dupes = {i: ids.count(i) for i in set(ids) if ids.count(i) > 1}
print('duplicate ids:', dupes or 'none')

EXPECTED = {'foundations': 42, 'core': 142, 'reps': 113, 'stretch': 17}
assert counts == EXPECTED, f'tier counts drifted: {counts} != {EXPECTED}'
assert len(problems) == 314, f'expected 314 problems, got {len(problems)}'
assert not dupes, f'duplicate ids: {dupes}'
print('counts match the document')

OUT.mkdir(parents=True, exist_ok=True)
json.dump(problems, open(OUT / 'problems.json', 'w'), indent=1, ensure_ascii=False)

# ---- Cue -> pattern table (the curriculum's stated "object of study").
# Two columns split by 2+ spaces; the left cell wraps onto a continuation line
# that has no right-hand column, so fold those back into the previous row.
cues, start = [], next(n for n, l in enumerate(lines) if l.startswith('WHAT THE PROBLEM SAYS'))
for ln in lines[start + 1:]:
    if ln.startswith('The three numbers to track'):
        break
    if not ln.strip():
        continue
    parts = re.split(r'\s{2,}', ln.strip())
    if len(parts) >= 2:
        cues.append({'says': parts[0].strip(), 'reach_for': ' '.join(parts[1:]).strip()})
    elif cues:
        cues[-1]['says'] += ' ' + parts[0].strip()   # wrapped left cell
print('cue rows:', len(cues))
json.dump(cues, open(OUT / 'cues.json', 'w'), indent=1, ensure_ascii=False)
