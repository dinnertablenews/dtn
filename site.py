#!/usr/bin/env python3
"""
Dinner Table News — the website.

Reads every published post in `posts/` and writes a static site to `site/`.

A post counts as published when it carries `published.json`: that file is written
only after Instagram accepts the post, so drafts, unused alternates and samples
never reach the web. That is why `2026-09-15-evening-alt` is on the site and
`2026-09-15-evening` is not — the alternate is the one that ran.

    python3 site.py                 build into site/
    python3 site.py --serve         build, then serve it on :8000
    DTN_BASE_URL=https://… site.py  build with absolute URLs (feed, sitemap, og:)

Every internal link is written relative to the page that carries it, so one build
works unchanged at a custom domain root, under github.io/dtn/, or opened from disk.

The display constants below — paper, ink, the three band hues — are render.py's,
restated rather than imported: render.py imports Playwright at module level and a
static site build has no business installing Chromium. If they move there, move
them here, or the site and the slides drift apart.
"""

import collections
import hashlib
import html
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
POSTS = ROOT / "posts"
OUT = ROOT / "site"

# ---- the parts Dan edits ---------------------------------------------------
SITE_NAME = "Dinner Table News"
INSTAGRAM = "https://instagram.com/dinnertablenews"
# The domain is authoritative: it goes in the CNAME file the deploy needs, and it is what
# the feed, the sitemap and the og: tags say. DTN_BASE_URL overrides it for a preview build.
DOMAIN = "dinnertablenews.com"
BASE_URL = (os.environ.get("DTN_BASE_URL") or (f"https://{DOMAIN}" if DOMAIN else "")).rstrip("/")
# Buttondown account name. It turns the signup form on; empty keeps the Instagram card,
# because a box that does nothing is worse than an honest link. The name is not a secret:
# it is in the form's action on every page, which is why it sits here and not in a repo
# secret. Cased exactly as Settings -> General shows it, because nothing here can tell us
# whether the endpoint folds case and a form that posts nowhere fails silently.
# DTN_BUTTONDOWN overrides it, and DTN_BUTTONDOWN="" turns the form off again.
BUTTONDOWN = os.environ.get("DTN_BUTTONDOWN", "DinnerTableNews")
EMAIL_FORM_ACTION = f"https://buttondown.com/api/emails/embed-subscribe/{BUTTONDOWN}" if BUTTONDOWN else ""
EMAIL_FIELD = "email"          # the field name Buttondown's embed expects
# Signup asks which ages a subscriber cares about. Everyone gets the same email --
# all three ages, one send -- so this is not segmentation yet; it is the data that
# would justify segmenting later, collected from the first subscriber rather than
# retrofitted onto a list that never recorded it.
# Buttondown reads an input named `tag` as a tag by name or id, so the three tags below
# have to exist in the Buttondown dashboard before the form goes live: a tag it does not
# recognise is dropped and the subscriber is saved without it, silently.
AGE_FIELD = "tag"              # "tag", or "metadata__ages" if tags are not available
AGE_VALUE = {b: f"ages-{b}" for b in ("5-7", "8-12", "13-17")}
START = "September 13, 2026"

# The first-visit walkthrough. Four steps, shown once, on the front page only.
# `sel` is the element it points at; a step whose element is missing is skipped, in
# whichever direction the reader is moving. A step with no `sel` centres instead.
TOUR = [
    # The first and last steps carry a title, set in the display serif. The blank line in
    # the last step is a real newline: .tour-t is set with textContent and given
    # white-space:pre-line, so the copy stays text and still breaks into paragraphs.
    {"sel": ".seg", "title": "Welcome to Dinner Table News, from Dan!",
     "text": "Pick your child\u2019s age and every part of this site adapts with suggested "
             "ways to talk about current news and age-appropriate questions for discussion, "
             "all guided by developmental psychology."},
    {"sel": ".stories article",
     "text": "Here is the most recent news story. Three are posted on this front page every "
             "day. You can find more on our Instagram page or in the Archive."},
    {"sel": "main .table-q",
     "text": "Tonight\u2019s dinner table question is related to the most recent news story "
             "and is meant for meaningful discussion for any age."},
    {"sel": "nav .nav-links", "title": "Thanks for visiting!",
     "text": "Visit the Archive to find news categories like Science or Business with "
             "suggested ways to talk about recent news.\n\n"
             "Share with a parent or friend, or follow us on Instagram @dinnertablenews!"},
]
# The prompt beside the age pills. One string: it used to be a parameter, and the
# archive and story pages quietly kept saying "Answers for my" after the front page
# changed.
AGE_PROMPT = "What can I say to my"
SHARE_SUBJECT = "Something for the dinner table"
SHARE_TEXT = ("Take a look at this site I found - Dinner Table News - that helps parents "
              "talk to their kids about today\u2019s news in age-appropriate language.")   # first post; the archive says how far back it goes

# ---- render.py's palette, restated (see the module docstring) --------------
PAPER, INK, SOFT, MUTED = "#F5F2EB", "#1B1A17", "#3D3A34", "#6B675F"
BANDS = ["5-7", "8-12", "13-17"]
LABEL = {"5-7": "5–7", "8-12": "8–12", "13-17": "13–17"}
HUES = {"5-7": 155, "8-12": 250, "13-17": 305}
DEFAULT_BAND = "8-12"
SLOTS = {"morning": ("Morning", 0), "noon": ("Noon", 1), "evening": ("Evening", 2)}

# The category list, in the order the archive shows it. Not alphabetical: it runs from
# the widest frame inward, and Good news sits last because it describes a tone rather
# than a subject.
CATEGORIES = ["World", "U.S.", "Politics", "Business", "Technology", "Science",
              "Health", "Climate", "Culture", "Sports", "Good news"]
# Posts published under the old list, mapped on the way in. Their covers still print the
# label they shipped with; this only governs how the site files and filters them.
# Both Security stories were a drone over Lithuania and a missile at Riyadh, so World.
REMAP = {"Government": "Politics", "Economy": "Business", "Security": "World"}
# "Good news" is a tone, not a subject, so it is a flag on the post rather than its
# category: the story still files under Science or Health, and the archive pill of that
# name filters on the flag. Without this, every positive story was lost to the one label
# and Science showed nothing despite a science source in the allowlist.
POSITIVE = "Good news"


def typo(s):
    """render.py's typographic pass, applied at render time only for the same reason:
    post.json keeps the straight marks the caption check compares against."""
    s = re.sub(r"(?<=\w)'(?=\w)", "’", s)
    s = re.sub(r'"([^"]*)"', "“\\1”", s)
    return s.replace("'", "’")


def e(s):
    """Escape for HTML text, after the typographic pass."""
    return html.escape(typo(str(s)), quote=True)


def attr(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- loading ---

def slot_of(slug, post):
    """Morning / Noon / Evening, from the slug where it says so and from the recorded
    slot time otherwise — `2026-09-14-test` published at 12:30 and reads as Noon."""
    tail = slug[11:]
    for key, (name, rank) in SLOTS.items():
        if tail.startswith(key):
            return name, rank
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", post.get("slot", ""))
    if m:
        hour = int(m.group(1))
        return ("Morning", 0) if hour < 10 else ("Noon", 1) if hour < 16 else ("Evening", 2)
    return "", 1


def load_posts():
    """Every published post, newest first. Tolerates the first three posts, which
    predate `date`, `cover_question` and `table_question`."""
    posts = []
    for d in sorted(POSTS.iterdir()):
        if not (d / "published.json").exists() or not (d / "post.json").exists():
            continue
        slug = d.name
        m = re.match(r"(\d{4}-\d{2}-\d{2})", slug)
        if not m:
            continue
        p = json.loads((d / "post.json").read_text())
        p["slug"] = slug
        p["category"] = REMAP.get(p.get("category", ""), p.get("category", ""))
        p["date"] = p.get("date") or m.group(1)
        p["day"] = date.fromisoformat(p["date"])
        # Not printed anywhere -- a reader gains nothing from "Noon" -- but by_day()
        # reads it to know a day has finished, and rank orders the posts within a date.
        p["slot_name"], rank = slot_of(slug, p)
        p["published"] = json.loads((d / "published.json").read_text())
        p["cover"] = d / "1-cover.jpg" if (d / "1-cover.jpg").exists() else None
        p["_sort"] = (p["date"], rank, slug)
        check_why(p)
        posts.append(p)
    posts.sort(key=lambda p: p["_sort"], reverse=True)
    return posts


def check_why(p):
    """A `why_long` may not run past the summary it sits beside. The reader came for the
    news; the note explaining how to talk about it is the smaller of the two, and once it
    is the bigger one the page reads as an essay with a story attached. render.py refuses
    a slide whose text crowds the card, and this is the same refusal for the same reason:
    a rule you can see is worth more than one in the spec."""
    cap = len(p.get("summary", ""))
    for band, a in p.get("ages", {}).items():
        t = a.get("why_long")
        if t and cap and len(t) > cap:
            raise SystemExit(
                f"WHY TOO LONG: {p['slug']} {band} -- why_long is {len(t)} characters "
                f"against a {cap}-character summary. Cut {len(t) - cap} more.")


def outlets():
    """The source list, read from feeds.yaml so the about page cannot drift from what the
    fetcher actually reads. A regex rather than a YAML library because this build has no
    dependencies and the file is ours: everything between `sources:` and `background:`,
    which leaves out NASA, whose feed supplies public-domain pictures and not stories."""
    text = (ROOT / "feeds.yaml").read_text()
    block = text.split("\nsources:", 1)[1].split("\nbackground:", 1)[0]
    names = re.findall(r"^\s*name:\s*(.+?)\s*$", block, re.M)
    if not names:
        raise SystemExit("site.py: no outlets found in feeds.yaml -- the about page needs them")
    return names


def and_list(items):
    """a, b and c"""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def long_date(d):
    return f"{d:%A, %B} {d.day}, {d.year}"


def short_date(d):
    return f"{d:%b} {d.day}"


def lead_question(p, band):
    """The question this band leads with. The cover question when it belongs to this
    band, so the page and the slide open the same way; otherwise the band's first."""
    cq = p.get("cover_question")
    if cq and cq.get("band") == band:
        for q in p.get("questions", {}).get(band, []):
            if q["q"] == cq["q"]:
                return q
        return {"q": cq["q"], "a": p.get("cover_answer", "")}
    qs = p.get("questions", {}).get(band, [])
    return qs[0] if qs else None


# ------------------------------------------------------------------- css ---

CSS = """
:root{
  --paper:#F5F2EB; --ink:#1B1A17; --soft:#3D3A34; --muted:#6B675F;
  --bg:var(--paper); --fg:var(--ink); --dim:var(--muted); --quiet:var(--soft);
  --rule:#E0DACD; --panel:#EDE8DE; --field:#FFFFFF;
  /* The walkthrough bubble sits on top of a dimmed page, so it cannot be the page's own
     background: on the dark theme that is #141311 on #141311 behind a scrim, and the
     panel has no edge. It gets a surface lifted well clear of the page, a border light
     enough to read against it, and a deeper scrim to sit on. */
  --tourbg:var(--bg); --tourline:var(--rule); --scrim:rgba(8,7,6,.68);
  /* The table question carries the three logo dots as a gradient. It is not the dots'
     own values: the bubble inverts by theme -- ink with paper text on paper, paper with
     ink text in the dark -- so each theme gets the three hues at a lightness its text
     can sit on. The quiet lines used to be var(--bg) at an opacity, which composited to
     4.0 against this gradient and was already at 3.4 against the flat dark bubble it
     replaces. They are solid mixes now, measured at 5.9 and up. */
  --tq1:oklch(0.30 0.09 155); --tq2:oklch(0.30 0.09 250); --tq3:oklch(0.30 0.09 305);
  --c57:oklch(0.48 0.13 155); --c812:oklch(0.48 0.13 250); --c1317:oklch(0.48 0.13 305);
  --tint57:oklch(0.94 0.035 155); --tint812:oklch(0.94 0.035 250); --tint1317:oklch(0.94 0.035 305);
  /* The card edge, which is the one place a band colour has to read as a COLOUR rather
     than as a darker line. On the dark theme the band is already light and chromatic and
     does that by itself; on paper, oklch 0.48 lands as a dark grey-blue, so the edge gets
     its own lighter, more saturated value. */
  --edge57:oklch(0.55 0.20 155); --edge812:oklch(0.55 0.20 250); --edge1317:oklch(0.55 0.20 305);
  --display:"Libre Caslon Display",Georgia,serif;
  --text:"Libre Caslon Text",Georgia,serif;
  --sans:"Instrument Sans",system-ui,-apple-system,sans-serif;
  color-scheme:light;
}
/* The system decides until the reader overrides it, and data-theme is how they do.
   The :not() guard is what lets an explicit "light" win against a dark OS. */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --edge57:var(--c57); --edge812:var(--c812); --edge1317:var(--c1317);
  --bg:#141311; --fg:#F1EDE4; --dim:#A8A295; --quiet:#C9C3B5;
  --rule:#2E2C27; --panel:#1D1C19; --field:#221F1B;
  --tourbg:#2B2925; --tourline:#4F4B43; --scrim:rgba(0,0,0,.80);
  --tq1:oklch(0.90 0.045 155); --tq2:oklch(0.90 0.045 250); --tq3:oklch(0.90 0.045 305);
  --c57:oklch(0.78 0.12 155); --c812:oklch(0.76 0.12 250); --c1317:oklch(0.78 0.12 305);
  --tint57:oklch(0.26 0.04 155); --tint812:oklch(0.26 0.04 250); --tint1317:oklch(0.26 0.04 305);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --edge57:var(--c57); --edge812:var(--c812); --edge1317:var(--c1317);
  --bg:#141311; --fg:#F1EDE4; --dim:#A8A295; --quiet:#C9C3B5;
  --rule:#2E2C27; --panel:#1D1C19; --field:#221F1B;
  --tourbg:#2B2925; --tourline:#4F4B43; --scrim:rgba(0,0,0,.80);
  --tq1:oklch(0.90 0.045 155); --tq2:oklch(0.90 0.045 250); --tq3:oklch(0.90 0.045 305);
  --c57:oklch(0.78 0.12 155); --c812:oklch(0.76 0.12 250); --c1317:oklch(0.78 0.12 305);
  --tint57:oklch(0.26 0.04 155); --tint812:oklch(0.26 0.04 250); --tint1317:oklch(0.26 0.04 305);
}

/* Derived from --tq2 so one set of rules serves both themes: on paper these step down
   toward the ink, in the dark they step down toward the paper. Percentages picked by
   rendering them over the gradient's worst stop and reading the pixels: 68% is 5.9:1,
   78% is 7.4:1, both clear of the 4.5 a 13px line needs. */
:root{
  --tqquiet:color-mix(in oklab, var(--bg) 68%, var(--tq2));
  --tqlabel:color-mix(in oklab, var(--bg) 78%, var(--tq2));
  --tqmid:color-mix(in oklab, var(--bg) 88%, var(--tq2));
}

/* The age is a document-level fact: one attribute on <html> colours and reveals
   the whole page, so switching it touches no element's inline style. */
html[data-band="5-7"]{--band:var(--c57); --bandtint:var(--tint57); --bandedge:var(--edge57)}
html[data-band="8-12"]{--band:var(--c812); --bandtint:var(--tint812); --bandedge:var(--edge812)}
html[data-band="13-17"]{--band:var(--c1317); --bandtint:var(--tint1317); --bandedge:var(--edge1317)}
[data-for]{display:none}
html[data-band="5-7"] [data-for="5-7"],
html[data-band="8-12"] [data-for="8-12"],
html[data-band="13-17"] [data-for="13-17"]{display:block}

*{box-sizing:border-box}
/* Clearance for the sticky header on an anchor jump, which has to be taller than the
   header or the target lands under it. It was 120px against a header of 138 on a phone
   and 160 on a tablet, so "Skip to the stories" put the first story 18px out of sight. */
html{scroll-padding-top:175px}
@media (max-width:640px){html{scroll-padding-top:150px}}
body{margin:0; background:var(--bg); color:var(--fg); font-family:var(--sans);
     font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased}
img{max-width:100%; display:block}
a{color:inherit}
.wrap{width:100%; max-width:var(--page,720px); margin:0 auto; padding-inline:20px}
body.wide{--page:1120px}      /* the front page: three stories abreast */
body.list{--page:880px}       /* the archive: a list, wider than prose but not by much */
.eyebrow{font-size:12px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--dim)}
.sep{opacity:.5; margin-inline:6px}
.skip{position:absolute; left:-9999px}
.skip:focus{left:20px; top:8px; z-index:40; background:var(--fg); color:var(--bg); padding:8px 14px; border-radius:3px}

/* ---- masthead ---------------------------------------------------- */
header{position:sticky; top:0; z-index:20; background:var(--bg); border-bottom:1px solid var(--rule)}
.bar{display:flex; align-items:center; justify-content:space-between; gap:16px; padding-block:14px}
/* render.py's wordmark(): three lines with the dots beneath, dot 45% of the type
   size and the gaps proportional to it, so the site and the slides carry one mark. */
.mark{display:inline-flex; flex-direction:column; align-items:flex-start; gap:9px;
      text-decoration:none; padding-block:2px}
.wm{font-family:var(--display); font-size:17px; line-height:1.0; letter-spacing:-.01em}
.dots{display:flex; gap:6px}
.dots i{width:8px; height:8px; border-radius:50%; display:block}
/* The mark is a stack now, so it is taller than it was, and the masthead is sticky.
   Scaled down on a phone to keep the whole sticky block near a seventh of the screen
   rather than a fifth: the pills below it are the part worth keeping on screen. */
@media (max-width:640px){
  .mark{gap:6px}
  .wm{font-size:14px}
  .dots{gap:5px}
  .dots i{width:6px; height:6px}
  .bar{padding-block:11px}
  .ages{padding-block:10px}
}
/* Desktop takes the mark at 27px, which is the size render.py prints on every slide, so
   the site and the carousels carry one mark at one size rather than two sizes of a
   similar idea. The dot stays 45% of the type and the gap 50%, the proportions the mark
   has always had, so it scales as a unit. The phone keeps 14px: the sticky block there
   is sized to leave the pills on screen, and this would take 40px of it. */
@media (min-width:940px){
  .mark{gap:13px}
  .wm{font-size:27px}
  .dots{gap:10px}
  .dots i{width:12px; height:12px}
  /* The header is 198px here rather than 160, so the clearance grows with it. */
  html{scroll-padding-top:215px}
}
/* On a phone the prompt cannot share a line with three pills, so it takes one of its
   own and the sticky block grows by a fifth for a line nobody needs: the pills read
   "5-7 year old". Hidden from the eye, kept for a screen reader, which still gets the
   group's own label. */
@media (max-width:560px){
  .ages .lab{position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%);
             white-space:nowrap}
}
nav{display:flex; gap:18px; font-size:14px}
/* The three links are a group of their own so the walkthrough can spotlight all of
   them at once -- and so the theme toggle, which is not a destination, stays out of it. */
.nav-links{display:flex; align-items:center; gap:18px}
nav a{color:var(--dim); text-decoration:none}
nav a:hover,nav a[aria-current="page"]{color:var(--fg)}
/* In the masthead Share is a nav item, not a button: the same size, colour and hover as
   the links beside it. It keeps class="share" so the one share handler still finds it. */
nav .nav-share{font:inherit; font-size:14px; font-weight:400; line-height:inherit;
  padding:0; border:0; border-radius:0; background:none; color:var(--dim); cursor:pointer}
nav .nav-share:hover{color:var(--fg)}
nav .nav-share:focus-visible{outline:2px solid var(--fg); outline-offset:3px}
.theme{display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px;
  padding:0; margin-left:-4px; border:0; border-radius:50%; background:transparent;
  color:var(--dim); cursor:pointer}
.theme:hover{color:var(--fg)}
.theme:focus-visible{outline:2px solid var(--fg); outline-offset:2px}
.bar nav{align-items:center}

/* ---- the age control: the whole idea of the site ------------------ */
.ages{display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding-block:12px; border-top:1px solid var(--rule)}
.ages .lab{font-size:13px; color:var(--dim)}
.seg{display:flex; gap:6px}
.seg button{font-family:var(--sans); font-size:14px; font-weight:500; cursor:pointer; white-space:nowrap;
  padding:7px 16px; border-radius:999px; background:transparent; color:var(--dim); border:1.5px solid var(--rule)}
@media (max-width:440px){.ages{gap:8px} .seg{gap:5px} .seg button{padding:7px 11px; font-size:13px}}
.seg button:hover{color:var(--fg)}
.seg button[data-band="5-7"]{--band:var(--c57); --bandtint:var(--tint57)}
.seg button[data-band="8-12"]{--band:var(--c812); --bandtint:var(--tint812)}
.seg button[data-band="13-17"]{--band:var(--c1317); --bandtint:var(--tint1317)}
.seg button[aria-pressed="true"]{color:var(--band); border-color:var(--band); background:var(--bandtint)}
.seg button:focus-visible{outline:2px solid var(--band); outline-offset:2px}

/* ---- today -------------------------------------------------------- */
/* The lede under this headline explained the control sitting directly above it, so it
   was instructions for a button you can already see. Dropping it, and tightening here,
   is worth about 50px of a phone screen before the first story. */
.today{padding-block:26px 6px}
.today h1{font-family:var(--display); font-weight:400; font-size:clamp(28px,6vw,38px);
          line-height:1.1; margin:6px 0 0; text-wrap:balance}
.today p{color:var(--dim); font-size:15px; margin:10px 0 0; max-width:46ch}

article{padding-block:34px; border-top:1px solid var(--rule)}
.cat{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
.cat b{font-weight:600; color:var(--band)}
/* The news, in ink at medium weight, under a marker stroke. The sans/serif split still
   carries the hierarchy: sans is the reporting, the serif question underneath is the kid.
   The marker is one fixed yellow in both themes rather than the age colour, which is
   already carrying the question's quote marks, the rule beside the answer and the card's
   hover edge -- a fourth use of it would stop meaning anything. Read it as a division of
   labour: the age colour is the kid's half of the card, the marker is the news half.
   The stroke is an SVG stretched to the line box, not a rectangle, so its edges run a
   little off-square the way a pen does; box-decoration-break paints it onto every line
   of a headline that wraps, and the line-height gives two strokes room not to touch.
   Ink on this yellow holds in both themes, so the text colour is fixed alongside it. */
.hl{font-family:var(--sans); font-size:17px; font-weight:500; line-height:1.5; color:var(--fg);
    margin:10px 0 0; max-width:52ch}
.hl a{text-decoration:none; color:#1B1A17; padding:2px 7px; margin-left:-7px;
  background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 20' preserveAspectRatio='none'%3E%3Cpath d='M1.4 3.4 C 26 1.1, 58 4.4, 98.7 1.9 L 99.3 17.1 C 71 19.8, 29 15.6, 0.7 18.4 Z' fill='%23F7E07A'/%3E%3C/svg%3E") 0 0 / 100% 100% no-repeat;
  box-decoration-break:clone; -webkit-box-decoration-break:clone}
.hl a:hover{text-decoration:underline; text-underline-offset:3px}
.q{font-family:var(--display); font-weight:400; font-size:clamp(30px,6.4vw,44px);
   line-height:1.04; letter-spacing:-.02em; margin:18px 0 0; text-wrap:balance}
.q .mk{color:var(--band)}
.a{font-family:var(--text); font-size:clamp(19px,3.6vw,21px); line-height:1.5; margin:16px 0 0;
   max-width:40ch; border-left:3px solid var(--band); padding-left:18px}
.src{font-size:13px; color:var(--dim); margin-top:18px; display:flex; gap:8px; flex-wrap:wrap; align-items:baseline}
.src a{text-decoration:underline; text-underline-offset:2px}
/* The three stories are cards: the whole card is the link, so it gets an edge to be
   the extent of. Border rather than a filled panel -- three filled blocks would shout
   over the type, which is the thing worth looking at. */
.stories{display:grid; gap:18px; margin-top:26px}
.stories article{border:1px solid var(--rule); border-radius:3px; padding:24px 22px;
  display:flex; flex-direction:column;
  transition:border-color .15s ease, background-color .15s ease}
.stories article.tappable{cursor:pointer}
.stories article:hover,
.stories article:focus-within{border-color:var(--bandedge); background:var(--panel)}
/* Stacked, not flowed: a long outlet name wraps the link onto a second line in one
   card and not the next, and two cards' footers stop lining up. Always two lines. */
.stories .src{margin-top:auto; padding-top:20px; flex-direction:column;
  align-items:flex-start; gap:7px}
/* The two links do different things, so they sit at opposite ends: the source leaves
   the site, the other goes further into it. */
.stories .src .more{align-self:flex-end}
.stories .hl a:hover{text-decoration:none}   /* the whole card is already the target */

/* Three abreast once there is room for three readable columns. The question steps
   down: 44px display type in a 340px column is a wall. */
@media (min-width:940px){
  body.wide .stories{grid-template-columns:repeat(3,1fr); gap:24px}
  body.wide .stories .q{font-size:clamp(24px,2.3vw,31px); margin-top:14px}
  body.wide .stories .a{font-size:18px; margin-top:14px}
  body.wide .search{max-width:520px}
  body.wide .today h1{font-size:44px}
}
/* Where the card cannot be hovered, the age's colour has no way to appear, so the whole
   border carries it instead of the neutral hairline. The query asks about hover rather
   than width because that is the actual reason: a tablet cannot hover either, and a
   desktop window dragged narrow still can. The border rather than a tint, which washes a
   whole page of same-age cards, or a shadow, which is invisible on the dark theme. */
@media (hover:none){
  .stories article{border-color:var(--band)}
}
@media (prefers-reduced-motion:reduce){.stories article{transition:none}}
.more{font-size:14px; color:var(--band); text-decoration:none; font-weight:500}
.more:hover{text-decoration:underline; text-underline-offset:3px}

/* ---- table question ------------------------------------------------ */
/* Inverted, the way the carousel's last slide is. It is the only dark thing on a light
   page and the only light thing on a dark one, which is the point: everything else here
   is something to read, and this is something to answer. Keyed to --fg/--bg rather than
   to ink so it inverts in both themes instead of just the one. */
.table-q{background:linear-gradient(103deg,var(--tq1),var(--tq2) 52%,var(--tq3));
         color:var(--bg); border-radius:18px; padding:32px 30px 34px;
         margin-block:12px 22px; position:relative}
/* The tail. Two borders on an empty box: a flat top the width of the tail and a
   transparent right edge, which leaves a triangle hanging off the bottom-left corner.
   18px of bottom margin above keeps it from landing on whatever follows. */
.table-q::after{content:""; position:absolute; left:34px; bottom:-17px; width:0; height:0;
  border-top:18px solid var(--tq1); border-right:20px solid transparent}
.table-q .basis{font-size:14px; line-height:1.45; margin:10px 0 0; max-width:60ch}
.table-q .basis .lab{color:var(--tqquiet)}
.table-q .basis .hd{color:var(--tqmid)}
.table-q .eyebrow{color:var(--tqlabel)}
.table-q h2{font-family:var(--display); font-weight:400; font-size:clamp(24px,5vw,32px);
            line-height:1.12; margin:12px 0 0; text-wrap:balance; color:var(--bg)}
.table-q p{font-size:14px; color:var(--tqquiet); margin:16px 0 0}

/* ---- blocks: archive, follow --------------------------------------- */
section.block{padding-block:34px; border-top:1px solid var(--rule)}
.block h2{font-family:var(--display); font-weight:400; font-size:26px; margin:8px 0 0}
.block p{color:var(--dim); font-size:15px; margin:10px 0 0; max-width:48ch}
.search{display:flex; gap:8px; margin-top:16px; flex-wrap:wrap}
.search input{flex:1 1 220px; min-width:0; font-family:var(--sans); font-size:15px; padding:11px 14px;
  border-radius:3px; border:1.5px solid var(--rule); background:var(--field); color:var(--fg)}
.search button{font-family:var(--sans); font-size:15px; font-weight:500; padding:11px 20px;
  border-radius:3px; border:1.5px solid var(--fg); background:var(--fg); color:var(--bg); cursor:pointer}
.chips{display:flex; flex-wrap:wrap; gap:8px; margin-top:14px}
.chips button,.chips span{font-family:var(--sans); font-size:13px; color:var(--dim); border:1px solid var(--rule);
  border-radius:999px; padding:5px 12px; background:transparent; cursor:pointer}
.chips button:hover:not([disabled]){color:var(--fg)}
.chips button[disabled]{opacity:.38; cursor:default}
.chips button[aria-pressed="true"]{color:var(--band); border-color:var(--band); background:var(--bandtint)}
.note{font-size:13px; color:var(--dim); margin-top:10px; min-height:1.2em}
.signup-done{font-size:17px; line-height:1.5; color:var(--band); margin:14px 0 0; max-width:46ch}
.ageask{border:0; margin:14px 0 0; padding:0; display:flex; flex-wrap:wrap; gap:8px; align-items:center}
.ageask legend{float:left; width:100%; font-size:13px; color:var(--dim); padding:0; margin-bottom:8px}
.agebox{display:inline-flex}
.agebox input{position:absolute; width:1px; height:1px; opacity:0; margin:0}
.agebox span{display:inline-block; font-size:14px; font-weight:500; cursor:pointer; white-space:nowrap;
  padding:7px 16px; border-radius:999px; border:1.5px solid var(--rule); color:var(--dim)}
.agebox:nth-of-type(1) span{--band:var(--c57); --bandtint:var(--tint57)}
.agebox:nth-of-type(2) span{--band:var(--c812); --bandtint:var(--tint812)}
.agebox:nth-of-type(3) span{--band:var(--c1317); --bandtint:var(--tint1317)}
.agebox input:checked + span{color:var(--band); border-color:var(--band); background:var(--bandtint)}
.agebox input:focus-visible + span{outline:2px solid var(--band); outline-offset:2px}
@media (max-width:440px){.agebox span{padding:7px 12px; font-size:13px}}
.follow-card{display:flex; gap:16px; align-items:center; margin-top:16px; padding:18px 20px;
  background:var(--panel); border-radius:3px; flex-wrap:wrap}
.follow-card .at{font-family:var(--display); font-size:19px}
/* The handle and two buttons want 322px and a phone gives the card 310. Shortening the
   label to "Share" bought 31px of that and left 12 short, so the row still broke. The
   gap, the card's own padding and the buttons give up a few pixels each rather than one
   of them giving up a lot: at 360px it now needs 281 against 292 available. */
@media (max-width:480px){
  .follow-card{gap:10px; padding:16px 14px}
  .follow-card .at{font-size:17px}
  .follow-card .btn,.follow-card .share{padding:10px 14px}
}
.btn{display:inline-block; font-size:15px; font-weight:500; padding:10px 18px; border-radius:3px;
  border:1.5px solid var(--fg); background:var(--fg); color:var(--bg); text-decoration:none}

/* ---- archive ---------------------------------------------------------- */
.stories article.hidden{display:none}
.count{font-size:13px; color:var(--dim); margin-top:16px}
.more-row{display:flex; justify-content:center; padding-block:10px 40px}
.more-btn{font-family:var(--sans); font-size:15px; font-weight:500; cursor:pointer;
  padding:11px 26px; border-radius:999px; border:1.5px solid var(--rule);
  background:transparent; color:var(--fg)}
.more-btn:hover{border-color:var(--fg)}
.more-btn:focus-visible{outline:2px solid var(--fg); outline-offset:2px}
.more-btn[hidden]{display:none}

/* ---- a single post --------------------------------------------------- */
/* A post is an <article> too, but it opens the page: it takes neither the rule
   between stories nor the space that rule needs. */
.post{padding-block:0; border-top:0}
.post > .head{padding-block:26px 0}
.post > .lede{padding-block:0 8px}

.post h1{font-family:var(--display); font-weight:400; font-size:clamp(30px,6.2vw,42px);
         line-height:1.08; margin:10px 0 0; text-wrap:balance; letter-spacing:-.01em}
.post .summary{font-family:var(--text); font-size:clamp(17px,3.2vw,19px); line-height:1.55;
               margin:18px 0 0; max-width:44ch; color:var(--quiet)}
.script{font-family:var(--text); font-size:clamp(19px,3.6vw,22px); line-height:1.5; margin:16px 0 0;
        max-width:42ch; border-left:3px solid var(--band); padding-left:18px}
.chip{display:inline-flex; align-items:center; gap:8px; font-size:13px; font-weight:500; color:var(--quiet);
      background:var(--panel); border-radius:999px; padding:6px 14px; margin-top:6px}
/* .block .why, not .why: the note is a <p> inside section.block, so `.block p` above
   outranked a bare .why and its margin never applied. */
.block .why{font-size:14px; color:var(--dim); margin:16px 0 0; max-width:46ch}
/* Stacked, the label lands straight under the script's quote rule and reads as the
   last line of it. A line's worth of air makes it the note about the script instead.
   Above 1000px the script and the note are in separate columns already. */
@media (max-width:999px){.block .why{margin-top:37px}}
.why b{color:var(--band); font-weight:600; letter-spacing:.08em; text-transform:uppercase; font-size:12px;
       display:block; margin-bottom:4px}
.asks{margin-top:26px; background:var(--bandtint); border-radius:3px; padding:22px 20px}
.asks .lab{font-size:12px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--band)}
.asks dl{margin:0}
.asks dt{font-family:var(--display); font-size:20px; line-height:1.2; margin-top:16px; text-wrap:balance}
.asks dd{font-family:var(--text); font-size:16px; line-height:1.5; color:var(--quiet); margin:6px 0 0}
.asks dd:before{content:"Try: "; font-family:var(--sans); font-size:12px; font-weight:600;
                letter-spacing:.08em; text-transform:uppercase; color:var(--dim)}
.others{font-size:14px; color:var(--dim); margin-top:22px}
.others button{font:inherit; color:var(--fg); background:none; border:0; padding:0; cursor:pointer;
               text-decoration:underline; text-underline-offset:3px}
.pager{display:flex; justify-content:space-between; gap:16px; padding-block:26px;
       border-top:1px solid var(--rule); font-size:14px}
.pager a{color:var(--dim); text-decoration:none; max-width:46%}
.pager a:hover{color:var(--fg)}
.pager .lab{display:block; font-size:12px; letter-spacing:.08em; text-transform:uppercase; margin-bottom:4px}

/* A text page takes the wide measure so its masthead matches every other page, and
   holds the reading column to what a reader can track. The rules between sections stop
   with the column: run to 1120 under a 480px column and the empty half looks like a
   layout that broke rather than a margin. */
body.text main.wrap > *{max-width:62ch}
.prose{max-width:60ch}

/* Wide screens: the dateline and headline span, and the summary and the age script sit
   side by side under them. Both columns take the same padding and the summary loses its
   top margin, so the two start on the same line rather than 18px apart. The rule that
   separated summary from ages when they were stacked moves under the headline, where it
   now separates one thing from two. */
@media (min-width:1000px){
  /* Two 410px columns and a 56px gutter. Everything below the article -- the pager, the
     follow card -- takes the same width, or the rules under a two-column story stop where
     the columns do not. */
  body.text main.wrap > *{max-width:876px}
  .post{display:grid; grid-template-columns:1fr 1fr; gap:0 56px; align-items:start}
  .post > .head{grid-column:1 / -1; border-bottom:1px solid var(--rule); padding-bottom:26px}
  .post > .lede{grid-column:1; grid-row:2; padding-block:30px 0}
  .post > section.block{grid-column:2; grid-row:2; padding-block:30px 0; border-top:0}
  .post > .lede .summary{margin-top:0}
  .post > .table-q{grid-column:1 / -1; grid-row:3; margin-top:36px}
}
.prose h2{font-family:var(--display); font-weight:400; font-size:24px; margin:34px 0 0}
.prose h3{font-family:var(--sans); font-size:14px; font-weight:600; letter-spacing:.04em;
  margin:24px 0 0; color:var(--band)}
.prose h3 .yr{color:var(--dim); font-weight:500; letter-spacing:0}
.prose .stage{border-left:2px solid var(--rule); padding-left:18px; margin-top:8px}
.prose .stage.b57{--band:var(--c57)} .prose .stage.b812{--band:var(--c812)}
.prose .stage.b1317{--band:var(--c1317)}
.prose .stage{border-left-color:var(--band)}
.prose p{font-size:15px; line-height:1.65; color:var(--quiet); margin:12px 0 0}
.prose a{text-decoration:underline; text-underline-offset:2px}

/* ---- share + first-visit walkthrough ---------------------------------- */
.share{font:inherit; font-size:15px; font-weight:500; cursor:pointer; padding:10px 18px;
  border-radius:3px; border:1.5px solid var(--rule); background:transparent; color:var(--fg)}
.share:hover{border-color:var(--fg)}
.share:focus-visible{outline:2px solid var(--fg); outline-offset:2px}

/* The dim is the hole's own box-shadow, so the panel itself is only the highlight.
   The backdrop is a separate full-screen layer, because a shadow does not take a
   click: without it a reader could tap a story card straight through the tour. */
.tour{position:fixed; inset:0; z-index:60}
.tour-hole{position:absolute; border-radius:6px; pointer-events:none;
  box-shadow:0 0 0 9999px var(--scrim); transition:top .2s ease, left .2s ease,
  width .2s ease, height .2s ease}
.tour-hole.none{box-shadow:0 0 0 9999px var(--scrim); width:0; height:0; top:50%; left:50%}
.tour-bub{position:absolute; width:min(340px, calc(100vw - 32px)); background:var(--tourbg);
  color:var(--fg); border:1px solid var(--tourline); border-radius:4px; padding:20px 20px 14px;
  box-shadow:0 14px 44px rgba(0,0,0,.34)}
.tour-bub.mid{position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); text-align:left}
.tour-n{font-size:12px; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
  color:var(--dim); margin:0}
.tour-h{font-family:var(--display); font-weight:400; font-size:24px; margin:10px 0 0}
/* pre-line so a step written as two paragraphs stays two paragraphs: the text is set
   with textContent, and a real newline is the only break that survives that. */
.tour-t{font-size:15px; line-height:1.55; color:var(--quiet); margin:10px 0 0;
  white-space:pre-line}
.tour-act{display:flex; align-items:center; gap:10px; margin-top:18px}
.tour-act .sp{flex:1}
.tour-skip{font:inherit; font-size:14px; background:none; border:0; color:var(--dim);
  cursor:pointer; padding:8px 4px; text-decoration:underline; text-underline-offset:3px}
.tour-skip:hover{color:var(--fg)}
.tour-next{font:inherit; font-size:15px; font-weight:500; cursor:pointer; padding:10px 20px;
  border-radius:3px; border:1.5px solid var(--fg); background:var(--fg); color:var(--bg)}
/* Back and Share are the same quiet button. Their edge is the bubble's, not the page's:
   --rule against the lifted dark surface is all but invisible. */
.tour-back{font:inherit; font-size:15px; font-weight:500; cursor:pointer; padding:10px 16px;
  border-radius:3px; border:1.5px solid var(--tourline); background:transparent; color:var(--fg)}
.tour-back:hover,.tour-bub .share:hover{border-color:var(--fg)}
.tour-bub .share{border-color:var(--tourline)}
.tour-next:focus-visible,.tour-skip:focus-visible,
.tour-back:focus-visible{outline:2px solid var(--fg); outline-offset:2px}
@media (prefers-reduced-motion:reduce){.tour-hole{transition:none}}

/* The footer sits outside <main>, beside the header rather than inside the article.
   It was the last child of main.wrap, which meant the 62ch cap the prose pages put on
   their article caught the footer too and it stopped short of the masthead above it.
   Its own .wrap now takes the page width, the way the header's does. */
/* The rule goes on the block inside the wrap, not the wrap: .wrap carries 20px of
   inline padding, so a border on it would overhang the content above by 20px a side. */
footer .wrap > div{border-top:1px solid var(--rule); padding-block:28px 40px}
footer{font-size:13px; color:var(--dim)}
footer a{text-decoration:underline; text-underline-offset:2px}
@media (prefers-reduced-motion:no-preference){.q,.a,.script{transition:opacity .18s ease}}
"""

# The stylesheet is the one file that changes on most deploys and the one file a browser
# is told it may keep. Fingerprinting the name means a changed stylesheet is a different
# URL, so a reader can never be served new markup against an old stylesheet -- which is
# how the archive once filtered correctly, reported the right count, and hid nothing.
CSS_NAME = f"site.{hashlib.sha256(CSS.encode()).hexdigest()[:10]}.css"

FONT_FACES = [
    ("Libre Caslon Display", 400, "libre-caslon-display-latin-400-normal.woff2"),
    ("Libre Caslon Text", 400, "libre-caslon-text-latin-400-normal.woff2"),
    ("Libre Caslon Text", 700, "libre-caslon-text-latin-700-normal.woff2"),
    ("Instrument Sans", 400, "instrument-sans-latin-400-normal.woff2"),
    ("Instrument Sans", 500, "instrument-sans-latin-500-normal.woff2"),
    ("Instrument Sans", 600, "instrument-sans-latin-600-normal.woff2"),
]


def font_css(up):
    return "\n".join(
        f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;font-display:swap;"
        f"src:url({up}assets/fonts/{f}) format('woff2')}}"
        for fam, w, f in FONT_FACES)


# -------------------------------------------------------------------- js ---

SHARE_JS = """
(function(){
  var URL_ = "__URL__" || location.href.split('#')[0];
  var MSG = "__MSG__", SUBJ = "__SUBJ__";
  function touch(){
    return window.matchMedia && window.matchMedia('(hover:none) and (pointer:coarse)').matches;
  }
  // A real anchor, clicked. `location.href = 'sms:...'` is a scripted app switch, and
  // Safari puts an "Allow ... to switch apps?" sheet in front of one -- with the raw
  // percent-encoded body printed in it. Clicking an <a> inside the same user gesture is
  // an ordinary navigation and goes straight to Messages.
  function go(href){
    var a=document.createElement('a');
    a.href=href; a.rel='noopener'; a.style.display='none';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ if(a.parentNode) a.parentNode.removeChild(a); }, 0);
  }
  // sms: is spelled differently by the two platforms; "?&body=" is the form both accept.
  function compose(){
    var body = MSG + "\\n\\n" + URL_;
    return touch()
      ? 'sms:?&body=' + encodeURIComponent(body)
      : 'mailto:?subject=' + encodeURIComponent(SUBJ) + '&body=' + encodeURIComponent(body);
  }
  window.dtnShare=function(){
    // On a phone, the native sheet: the reader picks Messages, Mail, AirDrop or anything
    // else they have, and no permission sheet appears at all. It has to be called
    // straight out of the click with nothing awaited first, or the gesture is spent.
    // Desktop stays on mailto, which is what it has always done.
    if(touch() && navigator.share){
      try{
        var r = navigator.share({title: SUBJ, text: MSG, url: URL_});
        if(r && r.catch) r.catch(function(err){
          // Cancelling the sheet is a choice, not a failure. Anything else, fall back.
          if(!err || err.name !== 'AbortError') go(compose());
        });
        return;
      }catch(err){}
    }
    go(compose());
  };
  var b=document.querySelectorAll('.share');
  for(var i=0;i<b.length;i++) b[i].addEventListener('click', window.dtnShare);
})();
"""

TOUR_JS = """
(function(){
  var KEY='dtn-tour', STEPS=__STEPS__;
  if(!document.querySelector('.stories')) return;          // front page only
  try{ if(localStorage.getItem(KEY)) return; }catch(e){ return; }
  var i=0, prev=document.activeElement, root=document.createElement('div');
  root.className='tour';
  root.innerHTML='<div class="tour-hole"></div>'+
    '<div class="tour-bub" role="dialog" aria-modal="true" aria-label="Getting started">'+
    '<p class="tour-n"></p><h2 class="tour-h" hidden></h2><p class="tour-t"></p>'+
    '<div class="tour-act"><button type="button" class="tour-skip">Skip</button>'+
    '<span class="sp"></span>'+
    '<button type="button" class="tour-back" hidden>Back</button>'+
    '<button type="button" class="tour-share share" hidden>Share</button>'+
    '<button type="button" class="tour-next">Next</button></div></div>';
  var hole=root.querySelector('.tour-hole'), bub=root.querySelector('.tour-bub'),
      next=root.querySelector('.tour-next'), share=root.querySelector('.tour-share'),
      back=root.querySelector('.tour-back'), skip=root.querySelector('.tour-skip');

  // A step whose element is not on the page is not a step. Everything that counts --
  // which step is next, which is previous, the "2 of 4" -- is asked of the steps that
  // are actually there, so going back skips the same gaps going forward skipped.
  function ok(n){ return n>=0 && n<STEPS.length &&
                         (!STEPS[n].sel || document.querySelector(STEPS[n].sel)); }
  function find(n,d){ while(n>=0 && n<STEPS.length && !ok(n)) n+=d;
                      return ok(n) ? n : -1; }
  function live(){ var a=[],n; for(n=0;n<STEPS.length;n++) if(ok(n)) a.push(n); return a; }

  function target(){ return STEPS[i].sel ? document.querySelector(STEPS[i].sel) : null; }
  function place(){
    var el=target();
    if(!el){ hole.className='tour-hole none'; bub.className='tour-bub mid';
             bub.style.top=bub.style.left=''; return; }
    hole.className='tour-hole';
    var r=el.getBoundingClientRect(), pad=8;
    hole.style.top=(r.top-pad)+'px'; hole.style.left=(r.left-pad)+'px';
    hole.style.width=(r.width+pad*2)+'px'; hole.style.height=(r.height+pad*2)+'px';
    bub.className='tour-bub';
    var bh=bub.offsetHeight, bw=bub.offsetWidth, gap=14, top=r.bottom+gap;
    if(window.innerHeight-r.bottom-gap < bh && r.top > bh+gap) top=r.top-bh-gap;
    bub.style.top=Math.max(12, Math.min(top, window.innerHeight-bh-12))+'px';
    bub.style.left=Math.max(12, Math.min(r.left, window.innerWidth-bw-12))+'px';
  }
  function draw(){
    var st=STEPS[i], h=root.querySelector('.tour-h'), seen=live();
    root.querySelector('.tour-n').textContent=(seen.indexOf(i)+1)+'/'+seen.length;
    h.textContent=st.title||''; h.hidden=!st.title;
    root.querySelector('.tour-t').textContent=st.text;
    var last=find(i+1,1)<0;
    next.textContent=last?'Done':'Next';
    share.hidden=!last;
    back.hidden=find(i-1,-1)<0;
    // On the last step Done already ends the tour, so Skip would be a second way to do
    // the same thing -- and a fourth button does not fit a 340px bubble.
    skip.hidden=last;
    var el=target();
    if(el){ if(el.closest('header')) window.scrollTo(0,0); else el.scrollIntoView({block:'center'}); }
    setTimeout(place,60);
    next.focus();
  }
  function end(){
    try{ localStorage.setItem(KEY,'1'); }catch(e){}
    root.remove();
    document.removeEventListener('keydown',key); window.removeEventListener('resize',place);
    window.removeEventListener('scroll',place);
    if(prev&&prev.focus) try{ prev.focus(); }catch(e){}
  }
  function key(ev){
    if(ev.key==='Escape'){ end(); return; }
    if(ev.key!=='Tab') return;                       // keep focus inside the dialog
    var f=bub.querySelectorAll('button:not([hidden])');
    if(!f.length) return;
    var first=f[0], lastEl=f[f.length-1];
    if(ev.shiftKey && document.activeElement===first){ ev.preventDefault(); lastEl.focus(); }
    else if(!ev.shiftKey && document.activeElement===lastEl){ ev.preventDefault(); first.focus(); }
  }
  next.addEventListener('click', function(){
    var n=find(i+1,1);
    if(n<0){ end(); return; }
    i=n; draw();
  });
  back.addEventListener('click', function(){
    var n=find(i-1,-1);
    if(n<0) return;
    i=n; draw();
  });
  skip.addEventListener('click', end);
  share.addEventListener('click', function(){ if(window.dtnShare) window.dtnShare(); });
  document.addEventListener('keydown', key);
  window.addEventListener('resize', place); window.addEventListener('scroll', place);
  // place() runs once, 60ms after a step is drawn. On a cold cache the webfonts land
  // after that, the prompt beside the age pills reflows, and the spotlight is left
  // pointing at where the pills used to be. A first visit is the only time the tour
  // runs, so a cold cache is the normal case, not the edge one.
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(place).catch(function(){});
  i=find(0,1);
  if(i<0) return;                                  // nothing on this page to point at
  document.body.appendChild(root);
  draw();
})();
"""

THEME_JS = """
(function(){
  var KEY='dtn-theme', root=document.documentElement, btn=document.getElementById('theme');
  if(!btn) return;
  function dark(){
    var t=root.getAttribute('data-theme');
    // No explicit choice yet, so report what the reader is actually looking at.
    if(t!=='dark'&&t!=='light')
      return window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches;
    return t==='dark';
  }
  function label(){
    btn.setAttribute('aria-label', dark()?'Switch to light theme':'Switch to dark theme');
  }
  btn.addEventListener('click', function(){
    var next = dark()?'light':'dark';
    root.setAttribute('data-theme', next);
    try{localStorage.setItem(KEY,next)}catch(e){}
    label();
  });
  // Until they choose, keep following the system if it changes under them.
  if(window.matchMedia){
    var mq=window.matchMedia('(prefers-color-scheme:dark)');
    var onchange=function(){ if(!root.getAttribute('data-theme')) label(); };
    mq.addEventListener? mq.addEventListener('change',onchange) : mq.addListener(onchange);
  }
  label();
})();
"""

CARD_JS = """
(function(){
  var cards=document.querySelectorAll('.stories article[data-href]');
  for(var i=0;i<cards.length;i++){
    cards[i].classList.add('tappable');   // added here so the cursor never lies to a
    cards[i].addEventListener('click', function(ev){   // reader with no JavaScript
      if(ev.target.closest('a,button')) return;            // a real link wins
      if(String(window.getSelection())) return;            // they were selecting text
      var href=this.getAttribute('data-href');
      if(ev.metaKey||ev.ctrlKey||ev.shiftKey) window.open(href,'_blank','noopener');
      else location.href=href;
    });
    // Middle-click opens a background tab everywhere else; it should here too.
    cards[i].addEventListener('auxclick', function(ev){
      if(ev.button!==1||ev.target.closest('a,button')) return;
      ev.preventDefault();
      window.open(this.getAttribute('data-href'),'_blank','noopener');
    });
  }
})();
"""

BAND_JS = """
(function(){
  var KEY='dtn-band', ok={'5-7':1,'8-12':1,'13-17':1}, root=document.documentElement;
  function sync(){
    var b=root.getAttribute('data-band');
    var btns=document.querySelectorAll('.seg button');
    for(var i=0;i<btns.length;i++)
      btns[i].setAttribute('aria-pressed', btns[i].getAttribute('data-band')===b?'true':'false');
  }
  window.dtnBand=function(b){
    if(!ok[b]) return;
    root.setAttribute('data-band',b);
    try{localStorage.setItem(KEY,b)}catch(e){}
    sync();
  };
  var btns=document.querySelectorAll('.seg button');
  for(var i=0;i<btns.length;i++)
    btns[i].addEventListener('click', function(){ window.dtnBand(this.getAttribute('data-band')); });
  sync();
  // Start the signup boxes on the age the reader has been reading at. On load only:
  // once they touch the boxes the answer is theirs, and switching the page age later
  // must not quietly rewrite what they said.
  var boxes=document.querySelectorAll('.agebox input');
  if(boxes.length){
    var cur=root.getAttribute('data-band');
    for(var j=0;j<boxes.length;j++) boxes[j].checked = boxes[j].getAttribute('data-band')===cur;
  }
})();
"""

SIGNUP_JS = """
(function(){
  // Buttondown's endpoint answers a form post with its own hosted page, so subscribing
  // threw the reader off the site onto somewhere they did not ask to be. Post it in the
  // background and answer here instead. The plain form is still the markup: with
  // JavaScript off this submits the old way and lands where it used to, which is worse
  // but works.
  var f=document.querySelector('form.signup');
  if(!f||!window.fetch) return;
  f.addEventListener('submit', function(ev){
    ev.preventDefault();
    var btn=f.querySelector('button[type=submit]');
    if(btn){ btn.disabled=true; btn.textContent='Sending'; }
    // no-cors, because the endpoint sends no CORS headers: the response comes back opaque
    // and its status cannot be read. So the copy promises the confirmation email rather
    // than a subscription, which is both the honest claim and the true one -- Buttondown
    // does not count anybody until they click that link.
    fetch(f.action, {method:'POST', mode:'no-cors',
                     body:new URLSearchParams(new FormData(f))})
      .catch(function(){})
      .then(function(){
        var p=document.createElement('p');
        p.className='signup-done';
        p.textContent='Check your inbox. There is a link there to confirm, and nothing '+
                      'arrives until you click it.';
        f.parentNode.replaceChild(p, f);
        var n=document.querySelector('#follow .note');
        if(n) n.textContent='Nothing in the inbox? Look in promotions or spam, and tell Dan.';
      });
  });
})();
"""

# Filters the archive list in the DOM rather than fetching an index: at a few hundred
# posts this is smaller and faster than a JSON round trip, and it works with the page
# opened from disk. Revisit when the archive runs to four figures.
# Filters and pages the cards already in the page rather than fetching an index: at a few
# hundred posts this is smaller and faster than a round trip, and it works from disk.
# Revisit when the archive runs to four figures and shipping every card stops being cheap.
ARCHIVE_JS = """
(function(){
  var PAGE=12, POSITIVE="__POSITIVE__";
  var list=document.getElementById('list'), input=document.getElementById('q'),
      note=document.getElementById('count'), more=document.getElementById('more'),
      chips=document.querySelectorAll('.chips button');
  if(!list) return;
  var cards=[].slice.call(list.querySelectorAll('article')), cat='', shown=PAGE;
  function draw(){
    var q=(input&&input.value||'').trim().toLowerCase(), n=0;
    for(var i=0;i<cards.length;i++){
      var c=cards[i];
      var byCat = cat===POSITIVE ? c.hasAttribute('data-positive')
                                 : c.getAttribute('data-cat')===cat;
      var hit=(!q||c.getAttribute('data-text').indexOf(q)>-1)&&(!cat||byCat);
      var vis=false;
      if(hit){ vis = n<shown; n++; }        // cards are already newest first
      c.classList.toggle('hidden',!vis);
    }
    if(note) note.textContent = n===0
      ? 'Nothing yet for that. Try a broader word.'
      : (q||cat) ? n+(n===1?' story':' stories')+'.'
                 : n+' stories since '+note.getAttribute('data-start')+'.';
    if(more){
      var left=n-shown;
      more.hidden = left<=0;
      more.textContent = left>PAGE ? 'Load 12 more' : 'Load '+left+' more';
    }
    var u=new URL(location); q?u.searchParams.set('q',q):u.searchParams.delete('q');
    history.replaceState(null,'',u);
  }
  function reset(){ shown=PAGE; draw(); }   // a new filter starts at the top again
  if(input){
    var pre=new URL(location).searchParams.get('q');
    if(pre) input.value=pre;
    input.addEventListener('input',reset);
  }
  for(var i=0;i<chips.length;i++) chips[i].addEventListener('click',function(){
    var v=this.getAttribute('data-cat'); cat=(cat===v?'':v);
    for(var j=0;j<chips.length;j++)
      chips[j].setAttribute('aria-pressed', chips[j].getAttribute('data-cat')===cat?'true':'false');
    reset();
  });
  if(more) more.addEventListener('click',function(){ shown+=PAGE; draw(); });
  var f=document.getElementById('searchForm');
  if(f) f.addEventListener('submit',function(ev){ev.preventDefault();reset();});
  draw();
})();
"""



SHARE_JS = (SHARE_JS.replace("__URL__", BASE_URL)
            .replace("__MSG__", SHARE_TEXT).replace("__SUBJ__", SHARE_SUBJECT))
TOUR_JS = TOUR_JS.replace("__STEPS__", json.dumps(TOUR))
ARCHIVE_JS = ARCHIVE_JS.replace("__POSITIVE__", POSITIVE)


# ----------------------------------------------------------------- shell ---

# Half-filled circle: the left half solid, the outline closing the right.
THEME_ICON = ('<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">'
              '<circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5"/>'
              '<path d="M10 1.75a8.25 8.25 0 0 0 0 16.5z" fill="currentColor"/></svg>')

DOTS = ('<span class="dots"><i style="background:var(--c57)"></i>'
        '<i style="background:var(--c812)"></i><i style="background:var(--c1317)"></i></span>')


def age_control():
    buttons = "".join(
        f'<button type="button" data-band="{b}" aria-pressed="{"true" if b == DEFAULT_BAND else "false"}">'
        f'{LABEL[b]} year old</button>' for b in BANDS)
    return (f'<div class="ages"><span class="lab">{e(AGE_PROMPT)}</span>'
            f'<div class="seg" role="group" aria-label="Choose your child’s age">{buttons}</div></div>')


def shell(*, up, title, desc, body, nav_here="", og_image=None, path="", band_control=True,
          extra_js="", og_type="website", width=""):
    def here(name):
        return ' aria-current="page"' if name == nav_here else ""

    og = ""
    if BASE_URL:
        url = f"{BASE_URL}/{path}" if path else f"{BASE_URL}/"
        og = (f'<link rel="canonical" href="{attr(url)}">'
              f'<meta property="og:url" content="{attr(url)}">')
        if og_image:
            og += (f'<meta property="og:image" content="{attr(BASE_URL + "/" + og_image)}">'
                   f'<meta name="twitter:card" content="summary_large_image">')
    if not og_image or not BASE_URL:
        og += '<meta name="twitter:card" content="summary">'

    return f"""<!doctype html>
<html lang="en" data-band="{DEFAULT_BAND}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{attr(title)}</title>
<meta name="description" content="{attr(desc)}">
<meta property="og:site_name" content="{attr(SITE_NAME)}">
<meta property="og:type" content="{attr(og_type)}">
<meta property="og:title" content="{attr(title)}">
<meta property="og:description" content="{attr(desc)}">
{og}
<link rel="icon" href="{up}assets/dots.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}assets/{CSS_NAME}">
<style>{font_css(up)}</style>
<script>try{{var r=document.documentElement,b=localStorage.getItem('dtn-band');
if(b==='5-7'||b==='8-12'||b==='13-17')r.setAttribute('data-band',b);
var t=localStorage.getItem('dtn-theme');if(t==='light'||t==='dark')r.setAttribute('data-theme',t);
}}catch(e){{}}</script>
</head>
<body class="{width}">
<a class="skip" href="#main">Skip to the stories</a>
<header>
  <div class="wrap">
    <div class="bar">
      <a class="mark" href="{up}"><span class="wm">Dinner<br>Table<br>News</span>{DOTS}</a>
      <nav>
        <span class="nav-links">
          <a class="nav-archive" href="{up}archive/"{here('archive')}>Archive</a>
          <a href="{up}about/"{here('about')}>About</a>
          <button type="button" class="nav-share share">Share</button>
        </span>
        <button class="theme" type="button" id="theme" aria-label="Switch to dark theme">{THEME_ICON}</button>
      </nav>
    </div>
    {age_control() if band_control else ""}
  </div>
</header>
<main class="wrap" id="main">
{body}
</main>
<footer>
  <div class="wrap">
    <div><a href="{attr(INSTAGRAM)}" rel="me">@dinnertablenews</a> · {e(SITE_NAME)}, {date.today().year}</div>
  </div>
</footer>
<script>{THEME_JS}{BAND_JS}{CARD_JS}{SHARE_JS}{SIGNUP_JS}{extra_js}</script>
</body>
</html>
"""


# ----------------------------------------------------------------- pages ---

def story_block(p, up, *, heading=False, filterable=False):
    """One story, written three ways; the age attribute on <html> picks which one shows."""
    bits = []
    href = f"{up}p/{p['slug']}/"
    label = f'{POSITIVE} \u00b7 {p["category"]}' if p.get("positive") else p["category"]
    meta = f'<b>{e(label)}</b><span class="eyebrow">{e(short_date(p["day"]))}'
    meta += "</span>"
    bits.append(f'<div class="cat eyebrow">{meta}</div>')
    headline = f'<a href="{href}">{e(p["headline"])}</a>'
    bits.append(f'<{"h2" if heading else "p"} class="hl">{headline}</{"h2" if heading else "p"}>')
    for band in BANDS:
        q = lead_question(p, band)
        if not q:
            continue
        bits.append(
            f'<div data-for="{band}">'
            f'<p class="q"><span class="mk">“</span>{e(q["q"])}<span class="mk">”</span></p>'
            f'<p class="a">{e(q["a"])}</p></div>')
    # The outlet name, and nothing else. The domain went first because it repeated the
    # outlet in smaller type; the sentence around it went next, because by the fourth
    # card a reader has worked out what a linked masthead under a story does.
    if p.get("source_url"):
        src = (f'Source: <a href="{attr(p["source_url"])}" rel="noopener">{e(p["outlet"])}</a>')
    else:
        src = f'Source: {e(p["outlet"])}'
    bits.append(f'<div class="src"><span>{src}</span><a class="more" href="{href}">'
                f'Dig further into this story →</a></div>')
    # data-href is what makes the card clickable. The headline stays a real link, so
    # the card still works with the script off, and for a keyboard and a crawler.
    extra = ""
    if filterable:
        # What the archive searches. Headline, summary, category, outlet and the three
        # lead questions: enough to find a story by what it was about or what a kid asked,
        # without carrying all three full scripts into the page for every post.
        parts = [p["headline"], p.get("summary", ""), p["category"], p["outlet"],
                 p.get("table_question", ""), POSITIVE if p.get("positive") else ""]
        for b in BANDS:
            lq = lead_question(p, b)
            if lq:
                parts.append(f'{lq["q"]} {lq["a"]}')
        text = " ".join(str(x) for x in parts).lower()
        extra = f' data-cat="{attr(p["category"])}" data-text="{attr(text)}"'
        if p.get("positive"):
            extra += ' data-positive="1"'
    return f'<article data-href="{attr(href)}"{extra}>{"".join(bits)}</article>'


def table_block(p, *, tonight=False):
    """The dinner table question, as something said rather than something printed: a
    speech bubble, with the headline it came from named above it."""
    if not p or not p.get("table_question"):
        return ""
    lab = "Tonight\u2019s dinner table question" if tonight else "The dinner table question"
    return (f'<div class="table-q"><div class="eyebrow">{e(lab)}</div>'
            f'<p class="basis"><span class="lab">Based on the headline:</span> '
            f'<span class="hd">{e(p["headline"])}</span></p>'
            f'<h2>{e(p["table_question"])}</h2></div>')


def follow_block(up):
    if EMAIL_FORM_ACTION:
        # Checked by default for the band the reader is already on, synced by JS on load.
        # Somebody who never touches these still tells us something, and a parent with a
        # 6-year-old and a 14-year-old can say so -- hence checkboxes, not a segment.
        boxes = "".join(
            f'<label class="agebox"><input type="checkbox" name="{attr(AGE_FIELD)}" '
            f'value="{attr(AGE_VALUE[b])}" data-band="{b}"'
            f'{" checked" if b == DEFAULT_BAND else ""}><span>{LABEL[b]}</span></label>'
            for b in BANDS)
        # embed=1 is what tells Buttondown the POST came from a form on someone else's
        # page. Without it the endpoint answers as if it were its own hosted page, and
        # a subscriber lands somewhere that does not look like this site.
        form = (f'<form class="signup" action="{attr(EMAIL_FORM_ACTION)}" method="post">'
                f'<input type="hidden" name="embed" value="1">'
                f'<div class="search"><input id="email" name="{attr(EMAIL_FIELD)}" type="email" '
                f'required placeholder="you@example.com" aria-label="Email address">'
                f'<button type="submit">Subscribe</button></div>'
                f'<fieldset class="ageask"><legend>Which ages are you most interested in?</legend>'
                f'{boxes}</fieldset></form>'
                f'<div class="note">Free. Sent at 7am. Unsubscribe whenever. Every email carries '
                f'all three ages — this just tells us who we’re writing for.</div>')
        return (f'<section class="block" id="follow"><div class="eyebrow">Every morning</div>'
                f'<h2>One email. Three stories. Words for your kid’s age.</h2>{form}</section>')
    # No provider yet, so no form: a box that does nothing is worse than an honest card.
    return (f'<section class="block" id="follow"><div class="eyebrow">Three times a day</div>'
            f'<h2>Follow along on Instagram.</h2>'
            f'<p>Morning, noon and evening — one story each, written for all three ages. '
            f'The morning email is coming; for now this is where it runs.</p>'
            f'<div class="follow-card"><span class="at">@dinnertablenews</span>'
            f'<a class="btn" href="{attr(INSTAGRAM)}">Follow</a>'
            f'<button type="button" class="share">Share</button>'
            f'</div></section>')


def render_index(posts, up=""):
    latest = posts[:3]
    lead = latest[0]
    stories = ('<div class="stories">'
               + "".join(story_block(p, up, heading=True) for p in latest) + "</div>")
    tq = next((p for p in latest if p.get("table_question")), None)
    table = table_block(tq, tonight=True) if tq else ""
    body = f"""
  <div class="today">
    <div class="eyebrow">{e(long_date(lead["day"]))}</div>
    <h1>How to talk to your kids about today’s news</h1>
  </div>
  {stories}
  {table}
  <section class="block" id="archive">
    <div class="eyebrow">Archive</div>
    <h2>Your kid just asked about something.</h2>
    <p>Every story since {e(START)}, searchable, each one still written for all three ages.</p>
    <form class="search" action="{up}archive/" method="get">
      <input id="q" name="q" type="search" placeholder="vaccines, war, tariffs, AI…"
             aria-label="Search the archive">
      <button type="submit">Search</button>
    </form>
  </section>
  {follow_block(up)}
"""
    return shell(up=up, title=f"{SITE_NAME} — today’s news, explained for your kid’s age",
                 desc="Three stories a day, each written three ways: for 5–7, 8–12 and 13–17. "
                      "Plus one question for the dinner table.",
                 body=body, width="wide", extra_js=TOUR_JS,
                 og_image=f"p/{lead['slug']}/cover.jpg" if lead["cover"] else None)


def render_archive(posts, up="../"):
    """Every story as a card, filtered in the browser, twelve at a time."""
    # Every category, in CATEGORIES order, so the set a reader sees is the set the site
    # commits to rather than whatever happens to have run. One with nothing behind it is
    # shown and disabled: a pill that returns "nothing yet" twice teaches people to stop
    # trusting the row.
    have = collections.Counter(p["category"] for p in posts)
    have[POSITIVE] = sum(1 for p in posts if p.get("positive"))
    chips = []
    for c in CATEGORIES:
        off = '' if have[c] else ' disabled aria-disabled="true" title="No stories yet"'
        chips.append(f'<button type="button" data-cat="{attr(c)}" aria-pressed="false"{off}>'
                     f'{e(c)}</button>')
    chips = "".join(chips)
    cards = "".join(story_block(p, up, heading=True, filterable=True) for p in posts)
    body = f"""
  <div class="today">
    <div class="eyebrow">Archive</div>
    <h1>Your kid just asked about something.</h1>
    <p>Every story since {e(START)}, still written for all three ages. Search it, or pick a
    category.</p>
  </div>
  <section class="block">
    <form class="search" id="searchForm" role="search">
      <input id="q" name="q" type="search" placeholder="vaccines, war, tariffs, AI\u2026"
             aria-label="Search the archive">
      <button type="submit">Search</button>
    </form>
    <div class="chips">{chips}</div>
    <div class="count" id="count" data-start="{attr(START)}"></div>
  </section>
  <div class="stories" id="list">{cards}</div>
  <div class="more-row"><button type="button" id="more" class="more-btn">Load more</button></div>
"""
    return shell(up=up, title=f"Archive \u2014 {SITE_NAME}",
                 desc=f"Every {SITE_NAME} story since {START}, each written for 5\u20137, "
                      f"8\u201312 and 13\u201317.",
                 body=body, nav_here="archive", path="archive/", extra_js=ARCHIVE_JS,
                 width="wide")


def render_post(p, newer, older, up="../../"):
    blocks = []
    for band in BANDS:
        a = p.get("ages", {}).get(band, {})
        qs = p.get("questions", {}).get(band, [])
        chip = f'<div class="chip">{e(a["chip"])}</div>' if a.get("chip") else ""
        shield = ('<div class="chip">Don’t raise it. If they hear it, say this:</div>'
                  if a.get("shield") else "")
        # The card's "why" is written to fit an Instagram slide, which is measured and can
        # fail the render. The site has no such ceiling, so a post may carry a longer one
        # written for this page; the slide never sees it.
        wtext = a.get("why_long") or a.get("why")
        why = (f'<p class="why"><b>Why it works</b>{e(wtext)}</p>') if wtext else ""
        asks = ""
        if qs:
            dl = "".join(f'<dt>“{e(q["q"])}”</dt><dd>{e(q["a"])}</dd>' for q in qs)
            asks = (f'<div class="asks"><div class="lab">They might ask</div><dl>{dl}</dl></div>')
        others = " and ".join(
            f'<button type="button" onclick="dtnBand(\'{b}\')">{LABEL[b]}</button>'
            for b in BANDS if b != band)
        blocks.append(
            f'<div data-for="{band}">'
            f'<div class="eyebrow" style="color:var(--band)">Ages {LABEL[band]}</div>'
            f'{shield or chip}'
            f'<p class="script">{e(a.get("script", ""))}</p>{why}{asks}'
            f'<p class="others">Also written for {others}.</p></div>')

    table = table_block(p)

    # As on the cards: one word saying what the link is, then the outlet.
    if p.get("source_url"):
        src = (f'Source: <a href="{attr(p["source_url"])}" rel="noopener">{e(p["outlet"])}</a>')
    else:
        src = f'Source: {e(p["outlet"])}'
    # A "What went out" block sat here: the carousel cover as a 120px thumbnail, a line saying
    # it ran on Instagram, a link to the post and the photo credit. It went because of what it
    # cost on a phone. The row wraps at every phone width, so the thumbnail took a line of its
    # own with 200px of nothing beside it and the text went under it: 259px of page for two
    # links. The follow block under the pager already says where the account is, and a reader
    # who wanted the carousel has read the whole story by then.
    pager = ""
    if newer or older:
        left = (f'<a href="{up}p/{newer["slug"]}/"><span class="lab">Newer</span>'
                f'{e(newer["headline"])}</a>') if newer else "<span></span>"
        right = (f'<a href="{up}p/{older["slug"]}/" style="text-align:right">'
                 f'<span class="lab">Older</span>{e(older["headline"])}</a>') if older else "<span></span>"
        pager = f'<div class="pager">{left}{right}</div>'

    meta = e(p["category"])
    meta += f'<br>{e(long_date(p["day"]))}'
    body = f"""
  <article class="post">
    <div class="head">
      <div class="eyebrow">{meta}</div>
      <h1>{e(p["headline"])}</h1>
    </div>
    <div class="lede">
      <p class="summary">{e(p.get("summary", ""))}</p>
      <div class="src"><span>{src}</span></div>
    </div>
    <section class="block">{"".join(blocks)}</section>
    {table}
  </article>
  {pager}
  {follow_block(up)}
"""
    q = lead_question(p, DEFAULT_BAND) or {}
    desc = p.get("cover_answer") or q.get("a") or p.get("summary", "")[:180]
    return shell(up=up, title=f'{p["headline"]} — {SITE_NAME}', desc=desc, body=body,
                 og_image=f"p/{p['slug']}/cover.jpg" if p["cover"] else None,
                 path=f"p/{p['slug']}/", og_type="article",
                 width="wide text")


ABOUT_TEMPLATE = """
  <div class="today">
    <div class="eyebrow">About</div>
    <h1>How this is made.</h1>
    <p>Three stories a day, each written three times.</p>
  </div>
  <section class="block"><div class="prose">
    <p>Tell a six-year-old that the president banned three news outlets from the White House
    and you will spend the next ten minutes explaining what a president is. Tell a
    fifteen-year-old the same thing and they will ask whether that is even legal, which is
    the better question anyway.</p>
    <p>Same story, two completely different problems. Most news written for kids solves
    neither, because it picks one imaginary child somewhere in the middle and writes for
    them.</p>

    <h2>What changes between five and fifteen</h2>
    <p>Jean Piaget got interested in how children think by noticing that they got the same
    questions wrong in the same ways. The errors had a pattern, and the pattern changed with
    age. The three bands here follow the stages he described.</p>

    <h3 class="b57">Ages 5–7 <span class="yr">· the end of the preoperational stage</span></h3>
    <div class="stage b57">
      <p>Thinking is still tied to what a child can see and handle. They reason well about a
      concrete thing and badly about an abstract one, and they tend to lock onto one feature
      of a problem and ignore the rest.</p>
      <p>So the 5–7 script starts with something physical. A toll on a bridge. A permission
      slip. A rule in a game. Then it says who is handling it. The abstraction gets cut
      because it does not land at this age, which is a different reason from protecting
      them.</p>
    </div>

    <h3 class="b812">Ages 8–12 <span class="yr">· concrete operational</span></h3>
    <div class="stage b812">
      <p>Now a kid can follow a chain of cause and effect, hold a rule in their head, and
      notice when somebody breaks it. This is the age that asks <em>why</em> and actually
      wants the answer. It is also the age that objects to a punishment before anyone has
      named the rule.</p>
      <p>So the 8–12 script hands over one mechanism they already understand, usually a
      referee or a thermostat, and one chain of consequence. Then it stops.</p>
    </div>

    <h3 class="b1317">Ages 13–17 <span class="yr">· formal operational</span></h3>
    <div class="stage b1317">
      <p>A teenager can reason about things that are not in front of them. A hypothetical.
      The distance between what somebody did and the reason they gave for doing it.</p>
      <p>So the 13–17 script opens with a question instead of an explanation and leaves the
      answer open. Hand a teenager a conclusion and you have told them the thinking is
      already finished.</p>
    </div>

    <h2>Read the kid, not the birthday</h2>
    <p>Piaget’s ages have been picked apart steadily since he set them. Later researchers
    kept finding children who could do things earlier than he expected once the task was put
    in familiar terms, and adults who reasoned inconsistently in the stage he assumed they
    had settled into.</p>
    <p>A nine-year-old who reads constantly might want the 13–17 version. A thirteen-year-old
    having a rough week might want the 8–12 one. Every story here carries all three, and the
    control at the top of the page moves whenever you want it to.</p>

    <h2>The words go to you</h2>
    <p>Lev Vygotsky’s idea was that there is a band of things a child cannot do alone but can
    do with a more capable person next to them, and that this is where the learning actually
    happens. Understanding an unresolved news story sits in that band for most kids.</p>
    <p>Which makes the useful thing to hand over the words an adult can say, rather than a
    simplified article for a kid to read by themselves. That is what the scripts are. The
    “why it works” line under each one tells you what the script is doing, so when your kid
    asks the question it did not anticipate, you are not guessing.</p>

    <h2>Why some stories say don’t raise it</h2>
    <p>Joanne Cantor spent years studying what frightens children about television and news,
    and found that the answer moves as they grow. Little kids react to how something looks
    and sounds. Older kids react to what it means: whether it is real, whether it can reach
    them, whether the adults have it handled.</p>
    <p>The uncomfortable consequence is that a story a six-year-old finds boring can
    frighten a twelve-year-old, who understood more of it. So some stories carry a flag
    telling you not to bring it up cold, with words ready in case they have already heard.
    Whether to raise it stays your call.</p>

    <h2>Why every story ends in a question</h2>
    <p>Deanna Kuhn’s work on how people learn to argue points at something inconvenient for
    parents: reasoning improves through practice in real dialogue, not through being taught.
    Kids move from treating claims as plain facts, through a stretch where every opinion
    looks equally good, toward weighing claims against evidence. They get there by arguing
    with people who take their answers seriously.</p>
    <p>News is good material for that. It is real, it is unfinished, and it usually has more
    than one defensible answer. So each story ends on a question that needs no background and
    has no settled answer. A six-year-old and a fifteen-year-old can both take a swing at it.</p>

    <h2>Where the news comes from</h2>
    <p>A fixed list of news outlets checked every hour, including {sources}. Every story names
    its outlet and links to the original reporting, and no quote, number or name appears here
    that the reporting does not carry.</p>
    <p>Photographs come from Wikimedia Commons under a Creative Commons or public domain
    licence, and are credited in the Instagram post they run with.</p>
    <p>This tool was built mostly late at night by me, a guy named Dan trying to figure out
    how to talk to my young kiddos about tough news while encouraging them to engage the
    world. The daily posts are produced with combined human and AI input. I am committed to
    not adding more AI slop to the world while also trying to stay technologically
    efficient.</p>
  </div></section>
"""

ABOUT = ABOUT_TEMPLATE.replace("{sources}", e(and_list(outlets())))


# ----------------------------------------------------------------- build ---

def dots_svg():
    """The three age dots on an ink tile: the Instagram avatar, redrawn for a 16px tab.

    render.py's lockup spaces the dots at 0.8 of their diameter. Held to that here the
    dots have to shrink to fit three of them plus two wide gaps, and at 16px they lose
    the colour that is the whole point of them. Held at the 0.1 this file used to carry,
    they merge into one bar. Half a diameter is the size where three dots still read as
    three at 16px and each one still reads as green, blue or purple — an optical
    correction for one size, not a second lockup.
    """
    d, ratio, box = 6.4, 0.5, 32
    gap = d * ratio
    x = (box - (3 * d + 2 * gap)) / 2 + d / 2      # centre the row, then the first centre
    dots = "".join(
        f'<circle cx="{x + i * (d + gap):.2f}" cy="{box / 2}" r="{d / 2:.2f}" fill="{c}"/>'
        for i, c in enumerate(("oklch(0.78 0.12 155)", "oklch(0.76 0.12 250)",
                               "oklch(0.78 0.12 305)")))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {box}">'
            f'<rect width="{box}" height="{box}" rx="7" fill="{INK}"/>{dots}</svg>')


DOTS_SVG = dots_svg()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rfc822(ts):
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


def by_day(posts):
    """Posts grouped by date, newest day first, each day's stories in slot order.

    Only days that ran their evening slot. A digest is a finished day: sending one at 7am
    while the day is still filling would mail a third of it and leave no way to send the rest.

    And never the newest day that has posts, even when it is finished. The evening publish
    is what finishes a day, it lands around 19:10 CT, and it rebuilds the site -- so a day
    released the moment it finished would enter the feed that night and Buttondown would mail
    it at seven in the evening under a page that promises seven in the morning. Holding it
    until a newer day has posted moves its first appearance to the next morning's publish,
    which is the send the page describes. Nothing is lost: the item is the same, a few hours
    later, and the stories have been on the site and on Instagram all along."""
    days = {}
    for p in posts:
        days.setdefault(p["date"], []).append(p)
    newest = max(days, default=None)
    out = []
    for d in sorted(days, reverse=True):
        if d == newest:
            continue
        stories = sorted(days[d], key=lambda p: p["_sort"])
        if any(p["slot_name"] == "Evening" for p in stories):
            out.append((d, stories))
    return out


# The three band hues as hex, for email only. They are the light-mode oklch() values
# converted once: plenty of mail clients still do not parse oklch(), and one that does
# not drops the colour to black rather than approximating it.
MAIL_HUE = {"5-7": "#00723B", "8-12": "#0C60A3", "13-17": "#6F4797"}
COUNT = {1: "One story", 2: "Two stories", 3: "Three stories", 4: "Four stories"}


def count_phrase(n):
    """Almost every day runs three slots, but the first day ran one and 14 September ran
    four. A subject line that says three when the email carries one is the kind of small
    lie a reader notices."""
    return COUNT.get(n, f"{n} stories")


def digest_html(stories, day):
    """One day as email HTML. Inline styles only and no class hooks: an email client
    keeps neither. Every age goes in, because an email cannot switch between them the
    way the site does.

    The day and the headline live here rather than in the RSS <title>. Buttondown uses the
    title as the subject line, and a subject line and an email's first heading are not the
    same job: one has 35 characters in a phone's inbox and has to earn the open, the other
    is already open. Printing both was the duplicate in the preview. This is the one that
    stays, because it renders inside the 560px column in the fonts and colours we set."""
    SERIF = "Georgia,'Times New Roman',serif"
    SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
    out = [f'<div style="font-family:{SANS};color:#1B1A17;max-width:560px">']
    out.append(f'<p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;'
               f'color:#6B675F;margin:0 0 6px">{e(long_date(day))}</p>')
    out.append(f'<p style="font-family:{SERIF};font-size:26px;line-height:1.15;margin:0 0 4px">'
               f'{e(count_phrase(len(stories)))}, and the words for them.</p>')
    first = False
    for p in stories:
        url = f"{BASE_URL}/p/{p['slug']}/"
        out.append('<hr style="border:0;border-top:1px solid #E0DACD;margin:28px 0 20px">')
        out.append(f'<p style="font-size:12px;font-weight:600;letter-spacing:.1em;'
                   f'text-transform:uppercase;color:#6B675F;margin:0 0 8px">{e(p["category"])}</p>')
        out.append(f'<p style="font-family:{SERIF};font-size:22px;line-height:1.2;margin:0 0 10px">'
                   f'{e(p["headline"])}</p>')
        if p.get("summary"):
            out.append(f'<p style="font-size:15px;line-height:1.55;color:#3D3A34;margin:0 0 18px">'
                       f'{e(p["summary"])}</p>')
        for band in BANDS:
            a = p.get("ages", {}).get(band, {})
            if not a.get("script"):
                continue
            col = MAIL_HUE[band]
            out.append(f'<p style="font-size:12px;font-weight:600;letter-spacing:.1em;'
                       f'text-transform:uppercase;color:{col};margin:16px 0 6px">'
                       f'Ages {LABEL[band]}</p>')
            out.append(f'<p style="font-family:{SERIF};font-size:16px;line-height:1.5;margin:0;'
                       f'padding-left:14px;border-left:3px solid {col}">{e(a["script"])}</p>')
            for q in p.get("questions", {}).get(band, []):
                out.append(f'<p style="font-size:14px;line-height:1.5;color:#3D3A34;margin:10px 0 0;'
                           f'padding-left:14px">&ldquo;{e(q["q"])}&rdquo;<br>'
                           f'<span style="color:#6B675F">Try: {e(q["a"])}</span></p>')
        if p.get("table_question"):
            out.append(f'<p style="background:#EDE8DE;padding:16px;margin:20px 0 0;font-family:{SERIF};'
                       f'font-size:17px;line-height:1.3">{e(p["table_question"])}</p>')
        src = e(p["outlet"])
        if p.get("source_url"):
            src = f'<a href="{attr(p["source_url"])}" style="color:#6B675F">{src}</a>'
        out.append(f'<p style="font-size:13px;color:#6B675F;margin:14px 0 0">{src} '
                   f'\u00b7 <a href="{attr(url)}" style="color:#6B675F">Read it on the site</a></p>')
    out.append("</div>")
    return "".join(out)


def subject(stories):
    """The email's subject line, built from the day's categories.

    It was the day: "Three stories for Saturday, September 19, 2026". True, and the same
    shape every morning, which is how an inbox teaches somebody to skip a sender. The
    categories change -- Politics, U.S. and World on the 19th; Business, Technology and
    Science on the 17th -- so the line changes with them and says what the mail is about
    before anything else.

    Front-loaded because a phone shows about 35 characters. The account's name is not in it:
    the From name already says Dinner Table News twice over, and repeating it spends the
    only characters that could have carried news."""
    seen = []
    for p in stories:
        if p["category"] not in seen:
            seen.append(p["category"])
    cats = seen[0] if len(seen) == 1 else ", ".join(seen[:-1]) + " and " + seen[-1]
    return f"{cats}, explained for your kid"


def build_digest_feed(posts):
    """One item per finished day, carrying that day's three stories at all three ages.
    This is the feed the morning email is built from; feed.xml stays one item per story
    for anyone reading in a feed reader."""
    items = []
    for day, stories in by_day(posts)[:20]:
        d = date.fromisoformat(day)
        # No per-day page exists, so "view online" goes to the archive; each story in
        # the body links to its own page.
        url = f"{BASE_URL}/archive/"
        evening = next((p for p in stories if p["slot_name"] == "Evening"), stories[-1])
        heads = "; ".join(p["headline"] for p in stories)
        items.append(
            f"<item><title>{e(subject(stories))}</title>"
            f"<link>{attr(url)}</link>"
            f"<guid isPermaLink=\"false\">dtn-digest-{day}</guid>"
            f"<pubDate>{rfc822(evening['published'].get('timestamp', ''))}</pubDate>"
            f"<description>{e(heads)}</description>"
            f"<content:encoded><![CDATA[{digest_html(stories, d)}]]></content:encoded></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            f'<channel><title>{e(SITE_NAME)} \u2014 the daily email</title>'
            f'<link>{attr(BASE_URL)}/</link>'
            f'<description>One email a day: three stories, each written for 5\u20137, '
            f'8\u201312 and 13\u201317.</description>'
            f'<language>en-us</language>{"".join(items)}</channel></rss>\n')


def build_feed(posts):
    items = []
    for p in posts[:20]:
        url = f"{BASE_URL}/p/{p['slug']}/"
        q = lead_question(p, DEFAULT_BAND) or {}
        desc = " ".join(x for x in [p.get("cover_answer") or q.get("a", ""), p.get("summary", "")] if x)
        items.append(
            f"<item><title>{e(p['headline'])}</title><link>{attr(url)}</link>"
            f"<guid isPermaLink=\"true\">{attr(url)}</guid>"
            f"<category>{e(p['category'])}</category>"
            f"<pubDate>{rfc822(p['published'].get('timestamp', ''))}</pubDate>"
            f"<description>{e(desc)}</description></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<rss version="2.0"><channel><title>{e(SITE_NAME)}</title>'
            f'<link>{attr(BASE_URL)}/</link>'
            f'<description>Today’s news, explained for your kid’s age.</description>'
            f'<language>en-us</language>{"".join(items)}</channel></rss>\n')


def main():
    posts = load_posts()
    if not posts:
        sys.exit("site.py: no published posts found in posts/ — nothing to build.")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    write(OUT / "index.html", render_index(posts))
    write(OUT / "archive" / "index.html", render_archive(posts))
    write(OUT / "about" / "index.html",
          shell(up="../", title=f"About — {SITE_NAME}",
                desc="Where the news comes from, how the three versions are written, and who checks them.",
                body=ABOUT, nav_here="about", path="about/", band_control=False,
                width="wide text"))

    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        d = OUT / "p" / p["slug"]
        write(d / "index.html", render_post(p, newer, older))
        if p["cover"]:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p["cover"], d / "cover.jpg")

    write(OUT / "assets" / CSS_NAME, CSS)
    write(OUT / "assets" / "dots.svg", DOTS_SVG)
    fonts = OUT / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for _, _, f in FONT_FACES:
        shutil.copyfile(ROOT / "fonts" / f, fonts / f)

    # GitHub Pages runs Jekyll otherwise, which drops directories beginning with _
    # and slows every build down for nothing.
    write(OUT / ".nojekyll", "")

    # Deploying from Actions there is no branch for GitHub to keep the custom domain in,
    # so the domain has to travel in the artifact or a deploy can drop it.
    if DOMAIN:
        write(OUT / "CNAME", DOMAIN + "\n")

    if BASE_URL:
        write(OUT / "feed.xml", build_feed(posts))
        write(OUT / "feed-daily.xml", build_digest_feed(posts))
        urls = ["", "archive/", "about/"] + [f"p/{p['slug']}/" for p in posts]
        write(OUT / "sitemap.xml",
              '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              + "".join(f"<url><loc>{attr(BASE_URL)}/{u}</loc></url>" for u in urls)
              + "</urlset>\n")
        write(OUT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    else:
        write(OUT / "robots.txt", "User-agent: *\nAllow: /\n")

    print(f"site.py: {len(posts)} posts → {OUT}/  "
          f"({posts[-1]['date']} to {posts[0]['date']}"
          + (f", {BASE_URL}" if BASE_URL else ", relative URLs; set DTN_BASE_URL for feed + sitemap")
          + ")")

    if "--serve" in sys.argv:
        import http.server
        import socketserver
        os.chdir(OUT)
        print("serving http://localhost:8000/  (ctrl-c to stop)")
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", 8000), http.server.SimpleHTTPRequestHandler) as httpd:
            httpd.serve_forever()


if __name__ == "__main__":
    main()
