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
# A hosted provider's form-POST endpoint (Buttondown, Kit, Beehiiv…). While it is
# empty the follow section renders the Instagram card instead of a dead form.
# Buttondown account name. Setting it turns the signup form on; empty keeps the
# Instagram card, because a box that does nothing is worse than an honest link.
BUTTONDOWN = os.environ.get("DTN_BUTTONDOWN", "")
EMAIL_FORM_ACTION = f"https://buttondown.com/api/emails/embed-subscribe/{BUTTONDOWN}" if BUTTONDOWN else ""
EMAIL_FIELD = "email"          # the field name Buttondown's embed expects
# Signup asks which ages a subscriber cares about. Everyone gets the same email --
# all three ages, one send -- so this is not segmentation yet; it is the data that
# would justify segmenting later, collected from the first subscriber rather than
# retrofitted onto a list that never recorded it.
AGE_FIELD = "tag"              # "tag", or "metadata__ages" if tags are not available
AGE_VALUE = {b: f"ages-{b}" for b in ("5-7", "8-12", "13-17")}
START = "September 13, 2026"   # first post; the archive says how far back it goes

# ---- render.py's palette, restated (see the module docstring) --------------
PAPER, INK, SOFT, MUTED = "#F5F2EB", "#1B1A17", "#3D3A34", "#6B675F"
BANDS = ["5-7", "8-12", "13-17"]
LABEL = {"5-7": "5–7", "8-12": "8–12", "13-17": "13–17"}
HUES = {"5-7": 155, "8-12": 250, "13-17": 305}
DEFAULT_BAND = "8-12"
SLOTS = {"morning": ("Morning", 0), "noon": ("Noon", 1), "evening": ("Evening", 2)}


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
        p["date"] = p.get("date") or m.group(1)
        p["day"] = date.fromisoformat(p["date"])
        p["slot_name"], rank = slot_of(slug, p)
        p["published"] = json.loads((d / "published.json").read_text())
        p["cover"] = d / "1-cover.jpg" if (d / "1-cover.jpg").exists() else None
        p["_sort"] = (p["date"], rank, slug)
        posts.append(p)
    posts.sort(key=lambda p: p["_sort"], reverse=True)
    return posts


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
  --c57:oklch(0.48 0.13 155); --c812:oklch(0.48 0.13 250); --c1317:oklch(0.48 0.13 305);
  --tint57:oklch(0.94 0.035 155); --tint812:oklch(0.94 0.035 250); --tint1317:oklch(0.94 0.035 305);
  --display:"Libre Caslon Display",Georgia,serif;
  --text:"Libre Caslon Text",Georgia,serif;
  --sans:"Instrument Sans",system-ui,-apple-system,sans-serif;
  color-scheme:light;
}
/* The system decides until the reader overrides it, and data-theme is how they do.
   The :not() guard is what lets an explicit "light" win against a dark OS. */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --bg:#141311; --fg:#F1EDE4; --dim:#A8A295; --quiet:#C9C3B5;
  --rule:#2E2C27; --panel:#1D1C19; --field:#221F1B;
  --c57:oklch(0.78 0.12 155); --c812:oklch(0.76 0.12 250); --c1317:oklch(0.78 0.12 305);
  --tint57:oklch(0.26 0.04 155); --tint812:oklch(0.26 0.04 250); --tint1317:oklch(0.26 0.04 305);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --bg:#141311; --fg:#F1EDE4; --dim:#A8A295; --quiet:#C9C3B5;
  --rule:#2E2C27; --panel:#1D1C19; --field:#221F1B;
  --c57:oklch(0.78 0.12 155); --c812:oklch(0.76 0.12 250); --c1317:oklch(0.78 0.12 305);
  --tint57:oklch(0.26 0.04 155); --tint812:oklch(0.26 0.04 250); --tint1317:oklch(0.26 0.04 305);
}

/* The age is a document-level fact: one attribute on <html> colours and reveals
   the whole page, so switching it touches no element's inline style. */
html[data-band="5-7"]{--band:var(--c57); --bandtint:var(--tint57)}
html[data-band="8-12"]{--band:var(--c812); --bandtint:var(--tint812)}
html[data-band="13-17"]{--band:var(--c1317); --bandtint:var(--tint1317)}
[data-for]{display:none}
html[data-band="5-7"] [data-for="5-7"],
html[data-band="8-12"] [data-for="8-12"],
html[data-band="13-17"] [data-for="13-17"]{display:block}

*{box-sizing:border-box}
html{scroll-padding-top:120px}
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
/* On a phone the prompt cannot share a line with three pills, so it takes one of its
   own and the sticky block grows by a fifth for a line nobody needs: the pills read
   "5-7 year old". Hidden from the eye, kept for a screen reader, which still gets the
   group's own label. */
@media (max-width:560px){
  .ages .lab{position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%);
             white-space:nowrap}
}
nav{display:flex; gap:18px; font-size:14px}
nav a{color:var(--dim); text-decoration:none}
nav a:hover,nav a[aria-current="page"]{color:var(--fg)}
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
.today{padding-block:36px 8px}
.today h1{font-family:var(--display); font-weight:400; font-size:clamp(28px,6vw,38px);
          line-height:1.1; margin:6px 0 0; text-wrap:balance}
.today p{color:var(--dim); font-size:15px; margin:10px 0 0; max-width:46ch}

article{padding-block:34px; border-top:1px solid var(--rule)}
.cat{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
.cat b{font-weight:600; color:var(--band)}
.hl{font-family:var(--sans); font-size:17px; font-weight:400; line-height:1.4; color:var(--dim);
    margin:10px 0 0; max-width:52ch}
.hl a{text-decoration:none}
.hl a:hover{text-decoration:underline; text-underline-offset:3px}
.q{font-family:var(--display); font-weight:400; font-size:clamp(30px,6.4vw,44px);
   line-height:1.04; letter-spacing:-.02em; margin:18px 0 0; text-wrap:balance}
.q .mk{color:var(--band)}
.a{font-family:var(--text); font-size:clamp(19px,3.6vw,21px); line-height:1.5; margin:16px 0 0;
   max-width:40ch; border-left:3px solid var(--band); padding-left:18px}
.src{font-size:13px; color:var(--dim); margin-top:18px; display:flex; gap:8px; flex-wrap:wrap; align-items:baseline}
.src a{text-decoration:underline; text-underline-offset:2px}
/* Three stories abreast once there is room for three readable columns. Each keeps its
   own rule above it, so the grid reads as three columns of a paper rather than a row
   of cards. The question steps down: 44px display type in a 340px column is a wall. */
@media (min-width:940px){
  body.wide .stories{display:grid; grid-template-columns:repeat(3,1fr); gap:0 36px}
  /* Columns are only columns if they share a baseline. The stories differ in length,
     so the source line is pushed to the foot of each one and the three line up. */
  body.wide .stories article{padding-block:28px 34px; display:flex; flex-direction:column}
  body.wide .stories .src{margin-top:auto; padding-top:20px}
  body.wide .stories .q{font-size:clamp(24px,2.3vw,31px); margin-top:14px}
  body.wide .stories .hl{font-size:16px}
  body.wide .stories .a{font-size:18px; margin-top:14px}
  body.wide .search{max-width:520px}
  body.wide .today h1{font-size:44px}
}
.more{font-size:14px; color:var(--band); text-decoration:none; font-weight:500}
.more:hover{text-decoration:underline; text-underline-offset:3px}

/* ---- table question ------------------------------------------------ */
.table-q{background:var(--panel); border-radius:3px; padding:28px 24px; margin-block:12px 0}
.table-q h2{font-family:var(--display); font-weight:400; font-size:clamp(23px,4.8vw,30px);
            line-height:1.12; margin:10px 0 0; text-wrap:balance}
.table-q p{font-size:14px; color:var(--dim); margin:14px 0 0}

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
.chips button:hover{color:var(--fg)}
.chips button[aria-pressed="true"]{color:var(--band); border-color:var(--band); background:var(--bandtint)}
.note{font-size:13px; color:var(--dim); margin-top:10px; min-height:1.2em}
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
.btn{display:inline-block; font-size:15px; font-weight:500; padding:10px 18px; border-radius:3px;
  border:1.5px solid var(--fg); background:var(--fg); color:var(--bg); text-decoration:none}

/* ---- archive list --------------------------------------------------- */
.list{margin-top:8px}
.item{display:flex; gap:16px; padding-block:22px; border-top:1px solid var(--rule); align-items:flex-start}
.item.hidden{display:none}
.item .thumb{flex:0 0 84px; width:84px; border-radius:3px; overflow:hidden; background:var(--panel)}
.item .thumb img{aspect-ratio:4/5; object-fit:cover; width:100%}
.item .meta{font-size:12px; color:var(--dim); letter-spacing:.06em; text-transform:uppercase; font-weight:600}
.item h3{font-family:var(--display); font-weight:400; font-size:21px; line-height:1.18; margin:6px 0 0; text-wrap:balance}
.item h3 a{text-decoration:none}
.item h3 a:hover{text-decoration:underline; text-underline-offset:3px}
.item .ask{font-family:var(--text); font-size:16px; color:var(--quiet); margin:8px 0 0; max-width:46ch}
.count{font-size:13px; color:var(--dim); margin-top:16px}

/* ---- a single post --------------------------------------------------- */
/* A post is an <article> too, but it opens the page: it takes neither the rule
   between stories nor the space that rule needs. */
.post{padding-block:0; border-top:0}
.post h1{font-family:var(--display); font-weight:400; font-size:clamp(30px,6.2vw,42px);
         line-height:1.08; margin:10px 0 0; text-wrap:balance; letter-spacing:-.01em}
.post .summary{font-family:var(--text); font-size:clamp(17px,3.2vw,19px); line-height:1.55;
               margin:18px 0 0; max-width:44ch; color:var(--quiet)}
.script{font-family:var(--text); font-size:clamp(19px,3.6vw,22px); line-height:1.5; margin:16px 0 0;
        max-width:42ch; border-left:3px solid var(--band); padding-left:18px}
.chip{display:inline-flex; align-items:center; gap:8px; font-size:13px; font-weight:500; color:var(--quiet);
      background:var(--panel); border-radius:999px; padding:6px 14px; margin-top:6px}
.why{font-size:14px; color:var(--dim); margin:16px 0 0; max-width:46ch}
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
.ig{display:flex; gap:16px; align-items:center; margin-top:8px; flex-wrap:wrap}
.ig img{width:120px; border-radius:3px}
.pager{display:flex; justify-content:space-between; gap:16px; padding-block:26px;
       border-top:1px solid var(--rule); font-size:14px}
.pager a{color:var(--dim); text-decoration:none; max-width:46%}
.pager a:hover{color:var(--fg)}
.pager .lab{display:block; font-size:12px; letter-spacing:.08em; text-transform:uppercase; margin-bottom:4px}

.prose{max-width:60ch}
.prose h2{font-family:var(--display); font-weight:400; font-size:24px; margin:32px 0 0}
.prose p{font-size:15px; line-height:1.65; color:var(--quiet); margin:12px 0 0}
.prose a{text-decoration:underline; text-underline-offset:2px}

footer{border-top:1px solid var(--rule); padding-block:28px 40px; font-size:13px; color:var(--dim);
       display:grid; gap:10px}
footer a{text-decoration:underline; text-underline-offset:2px}
@media (prefers-reduced-motion:no-preference){.q,.a,.script{transition:opacity .18s ease}}
"""

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

# Filters the archive list in the DOM rather than fetching an index: at a few hundred
# posts this is smaller and faster than a JSON round trip, and it works with the page
# opened from disk. Revisit when the archive runs to four figures.
ARCHIVE_JS = """
(function(){
  var input=document.getElementById('q'), list=document.getElementById('list'),
      note=document.getElementById('count'), chips=document.querySelectorAll('.chips button');
  if(!list) return;
  var items=[].slice.call(list.querySelectorAll('.item')), cat='';
  function apply(){
    var q=(input&&input.value||'').trim().toLowerCase(), n=0;
    for(var i=0;i<items.length;i++){
      var it=items[i];
      var hit=(!q||it.getAttribute('data-text').indexOf(q)>-1)&&(!cat||it.getAttribute('data-cat')===cat);
      it.classList.toggle('hidden',!hit);
      if(hit) n++;
    }
    if(note) note.textContent = (q||cat)
      ? (n===0 ? 'Nothing yet for that. Try a broader word.' : n+(n===1?' story':' stories')+' found.')
      : items.length+' stories since '+note.getAttribute('data-start')+'.';
    var u=new URL(location); q?u.searchParams.set('q',q):u.searchParams.delete('q');
    history.replaceState(null,'',u);
  }
  if(input){
    input.addEventListener('input',apply);
    var pre=new URL(location).searchParams.get('q');
    if(pre) input.value=pre;
  }
  for(var i=0;i<chips.length;i++) chips[i].addEventListener('click',function(){
    var v=this.getAttribute('data-cat'); cat = (cat===v?'':v);
    for(var j=0;j<chips.length;j++)
      chips[j].setAttribute('aria-pressed', chips[j].getAttribute('data-cat')===cat?'true':'false');
    apply();
  });
  var f=document.getElementById('searchForm');
  if(f) f.addEventListener('submit',function(ev){ev.preventDefault();apply();});
  apply();
})();
"""


# ----------------------------------------------------------------- shell ---

# Half-filled circle: the left half solid, the outline closing the right.
THEME_ICON = ('<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">'
              '<circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5"/>'
              '<path d="M10 1.75a8.25 8.25 0 0 0 0 16.5z" fill="currentColor"/></svg>')

DOTS = ('<span class="dots"><i style="background:var(--c57)"></i>'
        '<i style="background:var(--c812)"></i><i style="background:var(--c1317)"></i></span>')


def age_control(prompt="Show me what to say to my"):
    buttons = "".join(
        f'<button type="button" data-band="{b}" aria-pressed="{"true" if b == DEFAULT_BAND else "false"}">'
        f'{LABEL[b]} year old</button>' for b in BANDS)
    return (f'<div class="ages"><span class="lab">{e(prompt)}</span>'
            f'<div class="seg" role="group" aria-label="Choose your child’s age">{buttons}</div></div>')


def shell(*, up, title, desc, body, nav_here="", og_image=None, path="", band_control=True,
          extra_js="", prompt="Show me what to say to my", og_type="website", width=""):
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
<link rel="stylesheet" href="{up}assets/site.css">
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
        <a href="{up}archive/"{here('archive')}>Archive</a>
        <a href="{up}about/"{here('about')}>About</a>
        <a href="{attr(INSTAGRAM)}" rel="me">Instagram</a>
        <button class="theme" type="button" id="theme" aria-label="Switch to dark theme">{THEME_ICON}</button>
      </nav>
    </div>
    {age_control(prompt) if band_control else ""}
  </div>
</header>
<main class="wrap" id="main">
{body}
<footer>
  <div>Sources are a fixed list of news outlets, published on every story. Nothing outside it is
  used, and no quote, number or name appears that the reporting doesn’t carry.</div>
  <div><a href="{attr(INSTAGRAM)}">@dinnertablenews</a> · {e(SITE_NAME)}, {date.today().year}</div>
</footer>
</main>
<script>{THEME_JS}{BAND_JS}{extra_js}</script>
</body>
</html>
"""


# ----------------------------------------------------------------- pages ---

def story_block(p, up, *, heading=False):
    """One story, written three ways; the age attribute on <html> picks which one shows."""
    bits = []
    href = f"{up}p/{p['slug']}/"
    meta = f'<b>{e(p["category"])}</b><span class="eyebrow">{e(short_date(p["day"]))}'
    if p["slot_name"]:
        meta += f'<span class="sep">·</span>{e(p["slot_name"])}'
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
    src = f'{e(p["outlet"])}'
    if p.get("source_url"):
        dom = p.get("source_domain") or re.sub(r"^www\.", "", p["source_url"].split("/")[2])
        src += f', <a href="{attr(p["source_url"])}" rel="noopener">{e(dom)}</a>'
    bits.append(f'<div class="src"><span>{src}</span><a class="more" href="{href}">'
                f'All three ages →</a></div>')
    return f'<article>{"".join(bits)}</article>'


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
        form = (f'<form class="signup" action="{attr(EMAIL_FORM_ACTION)}" method="post">'
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
            f'<a class="btn" href="{attr(INSTAGRAM)}">Follow</a></div></section>')


def render_index(posts, up=""):
    latest = posts[:3]
    lead = latest[0]
    stories = ('<div class="stories">'
               + "".join(story_block(p, up, heading=True) for p in latest) + "</div>")
    tq = next((p for p in latest if p.get("table_question")), None)
    table = ""
    if tq:
        table = (f'<div class="table-q"><div class="eyebrow">Tonight’s dinner table question</div>'
                 f'<h2>{e(tq["table_question"])}</h2>'
                 f'<p>Anyone can answer it, including the ones who didn’t read the news.</p></div>')
    body = f"""
  <div class="today">
    <div class="eyebrow">{e(long_date(lead["day"]))}</div>
    <h1>Three stories, and the words for them.</h1>
    <p>Every story below is written three ways. Pick your kid’s age once and the whole page follows.</p>
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
                 body=body, width="wide",
                 og_image=f"p/{lead['slug']}/cover.jpg" if lead["cover"] else None)


def render_archive(posts, up="../"):
    cats = sorted({p["category"] for p in posts})
    chips = "".join(f'<button type="button" data-cat="{attr(c)}" aria-pressed="false">{e(c)}</button>'
                    for c in cats)
    items = []
    for p in posts:
        q = lead_question(p, DEFAULT_BAND) or {}
        text = " ".join(str(x).lower() for x in [
            p["headline"], p.get("summary", ""), p["category"], p["outlet"],
            p.get("table_question", ""), q.get("q", ""), q.get("a", "")])
        thumb = (f'<a class="thumb" href="{up}p/{p["slug"]}/">'
                 f'<img src="{up}p/{p["slug"]}/cover.jpg" alt="" loading="lazy" width="84" height="105">'
                 f'</a>') if p["cover"] else ""
        asks = "".join(
            f'<p class="ask" data-for="{b}">“{e(lq["q"])}”</p>'
            for b in BANDS if (lq := lead_question(p, b)))
        meta = e(short_date(p["day"]))
        if p["slot_name"]:
            meta += f'<span class="sep">·</span>{e(p["slot_name"])}'
        items.append(
            f'<div class="item" data-cat="{attr(p["category"])}" data-text="{attr(text)}">{thumb}'
            f'<div><div class="meta">{e(p["category"])}<span class="sep">·</span>{meta}</div>'
            f'<h3><a href="{up}p/{p["slug"]}/">{e(p["headline"])}</a></h3>{asks}</div></div>')
    body = f"""
  <div class="today">
    <div class="eyebrow">Archive</div>
    <h1>Your kid just asked about something.</h1>
    <p>Every story since {e(START)}, still written for all three ages. Search it, or pick a category.</p>
  </div>
  <section class="block">
    <form class="search" id="searchForm" role="search">
      <input id="q" name="q" type="search" placeholder="vaccines, war, tariffs, AI…"
             aria-label="Search the archive">
      <button type="submit">Search</button>
    </form>
    <div class="chips">{chips}</div>
    <div class="count" id="count" data-start="{attr(START)}"></div>
  </section>
  <div class="list" id="list">{"".join(items)}</div>
"""
    return shell(up=up, title=f"Archive — {SITE_NAME}",
                 desc=f"Every {SITE_NAME} story since {START}, each written for 5–7, "
                      f"8–12 and 13–17.",
                 body=body, nav_here="archive", path="archive/", extra_js=ARCHIVE_JS,
                 prompt="Answers for my", width="list")


def render_post(p, newer, older, up="../../"):
    blocks = []
    for band in BANDS:
        a = p.get("ages", {}).get(band, {})
        qs = p.get("questions", {}).get(band, [])
        chip = f'<div class="chip">{e(a["chip"])}</div>' if a.get("chip") else ""
        shield = ('<div class="chip">Don’t raise it. If they hear it, say this:</div>'
                  if a.get("shield") else "")
        why = (f'<p class="why"><b>Why it works</b>{e(a["why"])}</p>') if a.get("why") else ""
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

    table = ""
    if p.get("table_question"):
        table = (f'<div class="table-q"><div class="eyebrow">The dinner table question</div>'
                 f'<h2>{e(p["table_question"])}</h2>'
                 f'<p>Ask it at any age. Anyone can answer it, including the ones who didn’t '
                 f'read the news.</p></div>')

    src = e(p["outlet"])
    if p.get("source_url"):
        dom = p.get("source_domain") or re.sub(r"^www\.", "", p["source_url"].split("/")[2])
        src += f', <a href="{attr(p["source_url"])}" rel="noopener">{e(dom)}</a>'
    credit = f'<span>{e(p["photo_credit"])}</span>' if p.get("photo_credit") else ""

    ig = ""
    link = p["published"].get("permalink")
    if link:
        thumb = (f'<a href="{attr(link)}"><img src="cover.jpg" alt="The cover of this post" '
                 f'width="120" height="150" loading="lazy"></a>') if p["cover"] else ""
        ig = (f'<section class="block"><div class="eyebrow">What went out</div>'
              f'<div class="ig">{thumb}<div><p>This ran as a five-card carousel on Instagram.</p>'
              f'<p><a class="more" href="{attr(link)}">See the post →</a></p></div></div></section>')

    pager = ""
    if newer or older:
        left = (f'<a href="{up}p/{newer["slug"]}/"><span class="lab">Newer</span>'
                f'{e(newer["headline"])}</a>') if newer else "<span></span>"
        right = (f'<a href="{up}p/{older["slug"]}/" style="text-align:right">'
                 f'<span class="lab">Older</span>{e(older["headline"])}</a>') if older else "<span></span>"
        pager = f'<div class="pager">{left}{right}</div>'

    meta = e(p["category"])
    if p["slot_name"]:
        meta += f'<span class="sep">·</span>{e(p["slot_name"])}'
    meta += f'<br>{e(long_date(p["day"]))}'
    body = f"""
  <article class="post">
    <div class="today">
      <div class="eyebrow">{meta}</div>
      <h1>{e(p["headline"])}</h1>
      <p class="summary">{e(p.get("summary", ""))}</p>
      <div class="src"><span>{src}</span>{credit}</div>
    </div>
    <section class="block">{"".join(blocks)}</section>
    {table}
  </article>
  {ig}
  {pager}
  {follow_block(up)}
"""
    q = lead_question(p, DEFAULT_BAND) or {}
    desc = p.get("cover_answer") or q.get("a") or p.get("summary", "")[:180]
    return shell(up=up, title=f'{p["headline"]} — {SITE_NAME}', desc=desc, body=body,
                 og_image=f"p/{p['slug']}/cover.jpg" if p["cover"] else None,
                 path=f"p/{p['slug']}/", prompt="Answers for my", og_type="article")


ABOUT = """
  <div class="today">
    <div class="eyebrow">About</div>
    <h1>How this is made.</h1>
    <p>Three stories a day, each written three ways, so the answer you give fits the kid asking.</p>
  </div>
  <section class="block"><div class="prose">
    <h2>What it is</h2>
    <p>Every morning, noon and evening one news story is picked and written out three times:
    for a 5–7 year old, an 8–12 year old and a 13–17 year old. Each version gives you
    the words — what to say, the questions they will ask back, and an answer to each. Every
    story ends with one question for the dinner table that anyone can answer, including the
    ones who didn’t read the news.</p>

    <h2>Where the news comes from</h2>
    <p>A fixed list of news outlets, checked hourly. Nothing outside that list is ever fetched,
    and every story on this site names the outlet it came from and links to the original
    reporting. No quote, number or name appears here that the reporting doesn’t carry.</p>

    <h2>Written with AI, reviewed by a human</h2>
    <p>The stories are drafted by AI from that reporting and reviewed by a person before they
    go out — there is a window on every post where it can be pulled. The Instagram account
    carries the AI-generated label. Photographs come from Wikimedia Commons under a Creative
    Commons or public-domain licence and are credited on the post.</p>

    <h2>What this is for</h2>
    <p>Not to tell your kid what to think. To hand you a version of the day’s news you can
    say out loud at the age they are, and one question worth arguing about over dinner.</p>
  </div></section>
"""


# ----------------------------------------------------------------- build ---

DOTS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#1B1A17"/>'
    '<circle cx="8.5" cy="16" r="3.4" fill="oklch(0.78 0.12 155)"/>'
    '<circle cx="16" cy="16" r="3.4" fill="oklch(0.76 0.12 250)"/>'
    '<circle cx="23.5" cy="16" r="3.4" fill="oklch(0.78 0.12 305)"/></svg>')


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

    Only days that ran their evening slot are returned. A digest is a finished day:
    sending one at 7am while the day is still filling would mail a third of it and
    leave no way to send the rest."""
    days = {}
    for p in posts:
        days.setdefault(p["date"], []).append(p)
    out = []
    for d in sorted(days, reverse=True):
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
    way the site does."""
    SERIF = "Georgia,'Times New Roman',serif"
    SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
    out = [f'<div style="font-family:{SANS};color:#1B1A17;max-width:560px">']
    out.append(f'<p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;'
               f'color:#6B675F;margin:0 0 6px">{e(long_date(day))}</p>')
    out.append(f'<p style="font-family:{SERIF};font-size:26px;line-height:1.15;margin:0 0 4px">'
               f'{e(count_phrase(len(stories)))}, and the words for them.</p>')
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
            f"<item><title>{e(f'{count_phrase(len(stories))} for {long_date(d)}')}</title>"
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
                body=ABOUT, nav_here="about", path="about/", band_control=False))

    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        d = OUT / "p" / p["slug"]
        write(d / "index.html", render_post(p, newer, older))
        if p["cover"]:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p["cover"], d / "cover.jpg")

    write(OUT / "assets" / "site.css", CSS)
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
