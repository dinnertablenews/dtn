#!/usr/bin/env python3
"""Flag candidate AI tells in the copy, for a person to judge.

CLAUDE.md holds the rule. This finds the patterns it names, in the rendered site and in
every post's written fields, and prints each with enough context to rule on.

It does not fail a build, and it is not a linter. Several of the patterns have honest uses
-- "France, Britain, Pakistan and Egypt" is four countries, not a rule-of-three, and
"Morning, noon and evening" is the posting schedule -- so a clean run is not the goal and a
flagged line is not automatically wrong. The goal is that nobody ships a tell without
having looked at it.

    python3 voice.py            # the built site and the posts
    python3 voice.py FILE ...   # any files, e.g. a README before committing it

CLAUDE.md itself lists every banned word, so scanning it flags all of them. That is
the list doing its job, not a finding.
"""
import glob
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent

# The prose fields of a post. Everything else in post.json is data.
FIELDS = ("headline", "summary", "cover_question", "cover_answer", "table_question",
          "script", "why", "why_long", "chip", "q", "a")

TELLS = {
    "rule of three": r"\b\w+, \w+,? and \w+\b",
    # The tell is the parallelism, not the adverb: "why not just stop?" is how a child
    # talks. Requiring the second half keeps the quoted questions out of the results.
    "not just / not only": r"\bnot (just|only)\b[^.?!]{0,70}?\b(but|it's|it is)\b",
    "not X but Y": r"\bis not [^.]{2,40}\bbut\b",
    "copula avoidance": r"\b(serves|stands) as\b|\bboasts\b|\brefers to\b",
    "trailing -ing analysis":
        r", \w*(highlight|underscor|emphasiz|showcas|reflect|symboliz|ensur|foster|contribut)\w*ing\b",
    "significance claim":
        r"\b(a testament to|indelible mark|evolving landscape|rich tapestry|marks a shift"
        r"|setting the stage for|underscores the importance)\b",
    "vague attribution":
        r"\b(experts (say|argue)|observers have|studies suggest|it is widely (regarded|seen))\b",
    "hedged wrap-up": r"\b(important to (note|remember)|worth noting|in conclusion|in summary|overall,)",
    "challenges formula": r"\bdespite (its|these|the) [^.]{0,40}challenges\b",
    "AI vocabulary":
        r"\b(delve\w*|crucial|pivotal|robust|vibrant|intricate\w*|meticulous\w*|enduring"
        r"|garner\w*|foster\w*|enhanc\w*|showcas\w+|underscor\w*|tapestry|groundbreaking"
        r"|renowned|nestled|valuable insights|align with|resonate with)\b",
}
DASHES = 4   # per block of prose; one is a choice, four is a habit


def strip_html(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def walk(node, out):
    """Every string under one of the prose field names, at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and k in FIELDS:
                out.append(v)
            else:
                walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


def scan(label, text):
    hits = 0
    for name, pat in TELLS.items():
        for m in re.finditer(pat, text, re.I):
            frag = text[max(0, m.start() - 60):m.end() + 45].strip()
            print(f"{label}\n    [{name}] …{frag}…")
            hits += 1
    n = text.count("—")
    if n >= DASHES:
        print(f"{label}\n    [em dashes] {n}")
        hits += 1
    return hits


def main(argv):
    import json
    total = 0
    if argv:
        for f in argv:
            t = pathlib.Path(f).read_text()
            total += scan(f, strip_html(t) if f.endswith((".html", ".htm")) else t)
    else:
        for f in sorted(glob.glob(str(ROOT / "site/**/index.html"), recursive=True)):
            total += scan(str(pathlib.Path(f).relative_to(ROOT)), strip_html(pathlib.Path(f).read_text()))
        for f in sorted(glob.glob(str(ROOT / "posts/*/post.json"))):
            out = []
            walk(json.loads(pathlib.Path(f).read_text()), out)
            total += scan(str(pathlib.Path(f).relative_to(ROOT)), " ".join(out))
    print(f"\n{total} to look at. Judge each one; see CLAUDE.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
