"""Build the frequently-asked pool from five public lists.

    python tools/build_frequent.py

Sources, and why each needs its own path:
  * LeetCode study plans (Top Interview 150, LeetCode 75, Top 100 Liked) come
    from leetcode.com/graphql. Introspection is disabled there, so the field
    names below are fixed -- `planSubGroups.slug`, not `subGroupSlug`.
  * Striver's A2Z is not fetchable from takeuforward.org: the page is client
    rendered and the backend rejects anything without an Origin header, then
    404s on every path guess. Codolio publishes the same sheet with each item
    resolved to a real problem, so it is read from there instead.
  * A2Z is 455 items but only 274 are LeetCode; the rest are TUF-native basics
    ("C++ Input / Output"), HackerRank, InterviewBit and SPOJ. Only the LeetCode
    subset is usable here, and it needs slug -> frontend id, which comes from a
    full pull of the problem set.
  * NeetCode 150 comes from neetcode-gh/leetcode's own .problemSiteData.json,
    not from a leetcode.com problem list. A public list works today but is one
    person's list: it can be renamed, made private or deleted, and it carries no
    categories. The repo is the project's own data, ships the roadmap group as
    `pattern`, and flags the 150 subset of its ~450 entries with `neetcode150`.
    (Verified identical to leetcode.com/problem-list/plakya4j: same 150 slugs.)

Deduplication is by LeetCode frontend id, which is the only stable key: titles
repeat and slugs change. A2Z lists some problems under two topics, so it
self-duplicates before any cross-list merging happens.
"""

import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "lcsr" / "data" / "frequent.json"

PLANS = {"top150": "top-interview-150", "lc75": "leetcode-75", "top100": "top-100-liked"}
A2Z = ("https://node.codolio.com/api/question-tracker/v2/sheet/"
       "get-sheet-data-by-slug/strivers-a2z-dsa-sheet")
NEETCODE = ("https://raw.githubusercontent.com/neetcode-gh/leetcode/main/"
            ".problemSiteData.json")

LABELS = {"top150": "Top Interview 150", "lc75": "LeetCode 75",
          "top100": "Top 100 Liked", "striver": "Striver A2Z",
          "neetcode150": "NeetCode 150"}


def post(url, payload, **headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0", **headers})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())


def get(url, **headers):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def neetcode_150(lc):
    """The 150 subset of neetcode's own problem data, with its roadmap group.

    `link` is a bare LeetCode slug with a trailing slash ("two-sum/"), so it
    resolves through the same slug -> frontend id map everything else uses.
    """
    out = []
    for r in get(NEETCODE):
        if not r.get("neetcode150"):
            continue
        hit = lc.get(r["link"].strip("/"))
        if not hit:
            continue
        out.append((int(hit["questionFrontendId"]), hit["titleSlug"], hit["title"],
                    r.get("pattern") or ""))
    return out


def all_leetcode_problems():
    q = ("query pl($limit:Int,$skip:Int){problemsetQuestionList: questionList("
         "categorySlug:\"\",limit:$limit,skip:$skip,filters:{}){total: totalNum "
         "questions: data { questionFrontendId title titleSlug difficulty isPaidOnly }}}")
    out, skip = {}, 0
    total = None
    while total is None or skip < total:
        d = post("https://leetcode.com/graphql",
                 {"query": q, "variables": {"limit": 100, "skip": skip}},
                 Referer="https://leetcode.com/problemset/")
        node = d["data"]["problemsetQuestionList"]
        total = node["total"]
        out.update({r["titleSlug"]: r for r in node["questions"]})
        skip += 100
        time.sleep(0.25)
    return out


def study_plan(slug):
    q = ("query d($slug:String!){studyPlanV2Detail(planSlug:$slug){name planSubGroups"
         "{slug name questions{questionFrontendId title titleSlug difficulty paidOnly}}}}")
    return post("https://leetcode.com/graphql", {"query": q, "variables": {"slug": slug}},
                Referer=f"https://leetcode.com/studyplan/{slug}/")["data"]["studyPlanV2Detail"]


def main():
    print("fetching leetcode problem set ...")
    lc = all_leetcode_problems()
    print(f"  {len(lc)} problems")

    entries, raw_counts = {}, Counter()

    def add(pid, slug, title, source, section):
        raw_counts[source] += 1
        rec = entries.setdefault(pid, {"id": pid, "title": title, "slug": slug,
                                       "lists": [], "sections": {}})
        if source not in rec["lists"]:
            rec["lists"].append(source)
        if section:
            rec["sections"].setdefault(source, section)

    for key, slug in PLANS.items():
        d = study_plan(slug)
        for grp in d["planSubGroups"]:
            for q in grp["questions"]:
                add(int(q["questionFrontendId"]), q["titleSlug"], q["title"], key, grp["name"])
        print(f"  {key}: {raw_counts[key]}")
        time.sleep(0.4)

    print("fetching neetcode 150 ...")
    for pid, slug, title, pattern in neetcode_150(lc):
        add(pid, slug, title, "neetcode150", pattern)
    print(f"  neetcode150: {raw_counts['neetcode150']}")

    print("fetching striver a2z ...")
    mappings = get(A2Z, Origin="https://codolio.com",
                   Referer="https://codolio.com/")["data"]["mappings"]
    skipped = Counter()
    for m in mappings:
        q = m.get("questionId") or {}
        if q.get("platform") != "leetcode":
            skipped[q.get("platform", "?")] += 1
            continue
        hit = lc.get(q.get("slug"))
        if not hit:
            skipped["unmatched-slug"] += 1
            continue
        section = " · ".join(x for x in (m.get("topic"), m.get("subTopic")) if x)
        add(int(hit["questionFrontendId"]), hit["titleSlug"], hit["title"], "striver", section)
    print(f"  striver: {raw_counts['striver']} leetcode items "
          f"(skipped non-leetcode: {dict(skipped)})")

    for r in entries.values():
        meta = lc.get(r["slug"], {})
        r["difficulty"] = meta.get("difficulty", "?")
        r["paid"] = bool(meta.get("isPaidOnly"))
        r["count"] = len(r["lists"])

    rows = sorted(entries.values(), key=lambda r: (-r["count"], r["id"]))

    total_raw = sum(raw_counts.values())
    print(f"\n{total_raw} raw entries -> {len(rows)} unique "
          f"({total_raw - len(rows)} duplicates collapsed)")
    print("overlap:", dict(sorted(Counter(r['count'] for r in rows).items())))

    # These are the published sizes of the three plans; if a fetch half-fails the
    # counts drift and the pool silently shrinks, so fail loudly instead.
    assert raw_counts["top150"] == 150, raw_counts["top150"]
    assert raw_counts["lc75"] == 75, raw_counts["lc75"]
    assert raw_counts["top100"] == 100, raw_counts["top100"]
    assert raw_counts["neetcode150"] == 150, raw_counts["neetcode150"]
    assert raw_counts["striver"] > 250, raw_counts["striver"]
    assert len({r["id"] for r in rows}) == len(rows), "duplicate id survived the merge"

    OUT.write_text(json.dumps({"labels": LABELS, "problems": rows},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
