#!/usr/bin/env python3
"""Render a Dinner Table News post (post.json) to five 1080x1350 JPGs.

usage: python render.py posts/2026-09-13-morning/post.json posts/2026-09-13-morning/
Slides: 1-cover, 2-ages-5-7, 3-ages-8-12, 4-ages-13-17, 5-table.
Fonts are self-hosted in fonts/. Requires playwright (chromium).

Layout rule (enforced, not auto-fixed). Every slide has a #text block and a #floor element that
must stay clear of it: on the cover the question (#text) above the age-chip row (#floor); on each
age card the "Why it works" line above the "They might ask" band, with at least MIN_GAP px of paper
between them and the band ending inside the card; on the table slide the comment line above the
save/send/follow block. A slide that fails is reported as a "TOO LOW:" line on stderr and the
script exits 1. Fix it by shortening text. Type sizes are never reduced to make room, so the three
age cards always match.

Named age rule. The cover names a real age inside the question's band ("So your 14-year-old asks")
rather than the bracket, and the caption names one age per band. All of them are drawn once and
written into post.json as `ages_named`, because a re-render must not move them and the cover and the
caption must name the same kid. Five is in the 5-7 band and never named. Only the age itself takes
the band's colour, so the line still reads as a sentence. The bracket is still on the floor chips
and on the age card the reader swipes to.

Cover question rule. Every cover question renders at QSIZE, one size on every cover, so covers
sitting next to each other in the grid match instead of stepping down on a long question. There is
no character cap: a question is too long only when it actually crowds the slide, which the layout
rule above already catches as "TOO LOW: 1-cover".

Hashtag rule (enforced, not auto-fixed). Exactly four tags: #Parenting, #KidsAndNews, one tag naming
what this story is about, #DinnerTableNews. The third slot is the only free one, and it is never a
category label — the cover already prints the category, so #Economy or #GoodNews spends a tag saying
nothing. check_hashtags() reports a "HASHTAGS:" line on stderr and the script exits 1.

Photo zoom rule (enforced, not auto-fixed). `photo_zoom` enlarges the picture inside the disc and
the crop still comes off the bottom and the sides, never the top. It exists because a Commons infobox
image is sometimes two photographs stacked in one file, which at zoom 1.0 renders as a doubled
picture. check_composite() reads the Commons credit beside the photo and reports a "PHOTO:" line when
such a file has no photo_zoom recorded; setting the field, at any value, is the run saying it looked.

Photo rule (enforced, not auto-fixed). The cover disc hangs off the top and right of the slide, so
only its lower-left part is visible. The photo is sized to that visible part and anchored to its TOP
edge, which means two things: it covers every on-slide pixel of the disc, so no strip of bare
category tint can show at an edge; and whatever the frame cannot fit is cropped off the BOTTOM, so a
crop never takes the subject's head. check_photo() re-measures the rendered image and reports a
"PHOTO:" line on stderr if either guarantee breaks.
"""
import base64, json, os, random, re, sys
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PAPER, INK, MUTED, SOFT = "#F5F2EB", "#1B1A17", "#6B675F", "#3D3A34"
HUES = {"5-7": 155, "8-12": 250, "13-17": 305}
LABEL = {"5-7": "5–7", "8-12": "8–12", "13-17": "13–17"}
NEXT = {"5-7": "Ages 8–12 →", "8-12": "Ages 13–17 →", "13-17": "One for the whole table →"}
CATS = {"Technology": "oklch(0.78 0.11 85)", "Health": "oklch(0.78 0.11 20)", "Economy": "oklch(0.78 0.10 190)",
        "Government": "oklch(0.78 0.10 240)", "Climate": "oklch(0.78 0.11 140)", "Science": "oklch(0.78 0.11 300)",
        "Culture": "oklch(0.78 0.12 350)", "Security": "oklch(0.70 0.04 60)", "Good news": "oklch(0.82 0.13 95)",
        "World": "oklch(0.78 0.10 215)", "Sports": "oklch(0.78 0.12 55)"}
QSIZE = 132             # every cover question renders at this size; length is bounded by the
                        # layout check (#text clear of #floor), not by a character count
SWIPE_TAGS = ["#Parenting", "#KidsAndNews"]   # every post opens with these two
BRAND_TAG = "#DinnerTableNews"                # and closes with this one
# Tags that tell a reader nothing the cover hasn't already told them: the category labels
# themselves (the cover prints the category), plus the catch-alls every news account uses.
# The one story tag has to be the thing the story is actually about.
GENERIC_TAGS = {t.replace(" ", "").lower() for t in
                ["Technology", "Health", "Economy", "Government", "Climate", "Science", "Culture",
                 "Security", "Good news", "World", "Sports", "News", "Politics", "Breaking news",
                 "Current affairs", "Daily news", "World news", "US news", "Kids", "Parenting tips"]}
MIN_GAP = 72            # age cards: paper between the why line and the band
GAP = {"1-cover": 45, "2-ages-5-7": MIN_GAP, "3-ages-8-12": MIN_GAP, "4-ages-13-17": MIN_GAP, "5-table": 45}
# Cover disc, positioned against the top-right corner of the 1080x1350 slide. It hangs off both
# edges, so only DISC_W x DISC_H of it is actually on the slide; that rectangle is what the photo
# has to fill. Deriving the photo box from these means the two can never drift apart.
DISC, DISC_TOP, DISC_RIGHT = 760, -240, -300
DISC_W = DISC + DISC_RIGHT      # 460px of the disc's width is on the slide
DISC_H = DISC_TOP + DISC        # 520px of its height is below the top edge
PHOTO_BLEED = 8                 # run the photo past the slide edge; rounding never exposes tint
def col(h, l=0.55, c=0.13): return f"oklch({l} {c} {h})"


def typo(s):
    """Straight marks to typographic ones, at render time only. The slides set the cover question in
    real curly quotes, so a typewriter apostrophe two inches above it in the headline showed. This
    never touches build_caption(): the caption stored in post.json stays byte-for-byte what the
    caption check compares against, and Instagram's own UI font renders straight marks fine."""
    s = re.sub(r"(?<=\w)'(?=\w)", "\u2019", s)          # don't, Trump's
    s = re.sub(r'"([^"]*)"', "\u201c\\1\u201d", s)      # a quoted phrase
    return s.replace("'", "\u2019")


# Five is in the band but never named. "Your 5-year-old asks" reads as a preschooler and the
# 5-7 script is written for a kid who has started school, so the named age is 6 or 7.
BAND_AGES = {"5-7": [6, 7], "8-12": [8, 9, 10, 11, 12], "13-17": [13, 14, 15, 16, 17]}


def ages_named(p):
    """One concrete age per band: "So your 14-year-old asks" reads like a real kid where a bracket
    reads like a form field. The cover names the one in its own band and the caption names all three,
    and they have to agree — a reel that says "your 16-year-old" over a caption that says "at 15" is
    two different kids. Drawn once and recorded as `ages_named` in post.json, the way publish_target
    records the publish minute: the shorten-and-re-render loop would otherwise redraw on every pass
    and drift from the veto notification, and the caption check compares against a stored string.
    `cover_age` is the field this replaced; a post that still carries one keeps that age."""
    got = dict(p.get("ages_named") or {})
    if p.get("cover_age"):
        got.setdefault(p["cover_question"]["band"], p["cover_age"])
    return {b: got.get(b) or random.choice(ages) for b, ages in BAND_AGES.items()}


def cover_age(p):
    return ages_named(p)[p["cover_question"]["band"]]


def photo_img(path, box_w, box_h, top=0, zoom=1.0, focus_x="50%"):
    """The duotone photo for the disc, as an <img> for a clipping parent.

    zoom enlarges the picture inside its box and the parent clips the overflow, so the crop still
    comes off the bottom and the sides and never off the top, per the photo rule. 1.0 is plain
    object-fit cover. Raise it when the frame is showing something it should not: a Commons infobox
    image is sometimes two photographs stacked in one file (White_House_north_and_south_sides.jpg),
    and a box taller than the source then fits the whole composite in, so the picture reads doubled."""
    b = base64.b64encode(photo_jpeg(path)).decode()
    w, h = box_w * zoom, box_h * zoom
    try: fx = float(str(focus_x).strip().rstrip("%")) / 100
    except ValueError: fx = 0.5
    return (f'<img id="photo" src="data:image/jpeg;base64,{b}" style="position:absolute;'
            f'left:{-(w - box_w) * fx + 0:.0f}px;top:{top}px;width:{w:.0f}px;height:{h:.0f}px;'
            f'object-fit:cover;object-position:{focus_x} 0%;display:block;'
            f'filter:grayscale(1) contrast(1.05);mix-blend-mode:multiply;opacity:0.9">')


def composite_source(p):
    """Commons credits a stacked composite by naming each half, e.g. artist "(top)X(bottom)Y". Those
    files render as two photographs in one disc unless photo_zoom picks one. Returns the credit."""
    ph = p.get("photo")
    if not ph: return None
    side = os.path.splitext(ph)[0] + ".json"
    if not os.path.exists(side): return None
    try: meta = json.load(open(side))
    except Exception: return None
    a = (meta.get("artist") or "")
    return a if ("(top)" in a and "(bottom)" in a) else None


def photo_jpeg(path):
    """The photo as JPEG bytes for embedding. No padding: cover() places and crops it explicitly."""
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88); return buf.getvalue()


def font_css():
    def face(fam, file, w):
        b = base64.b64encode((ROOT / "fonts" / file).read_bytes()).decode()
        return f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(data:font/woff2;base64,{b}) format('woff2');}}"
    return "".join([
        face("Libre Caslon Display", "libre-caslon-display-latin-400-normal.woff2", 400),
        face("Libre Caslon Text", "libre-caslon-text-latin-400-normal.woff2", 400),
        face("Libre Caslon Text", "libre-caslon-text-latin-700-normal.woff2", 700),
        face("Instrument Sans", "instrument-sans-latin-400-normal.woff2", 400),
        face("Instrument Sans", "instrument-sans-latin-500-normal.woff2", 500),
        face("Instrument Sans", "instrument-sans-latin-600-normal.woff2", 600)])


def page(bg, fg, body):
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}
html,body{{margin:0;background:{bg};color:{fg};font-family:"Instrument Sans",sans-serif;-webkit-font-smoothing:antialiased}}
.serif{{font-family:"Libre Caslon Text",serif}} .display{{font-family:"Libre Caslon Display",serif}}
</style></head><body>{body}</body></html>'''


def dots(size, gap, l):
    return ('<div style="display:flex;gap:%dpx">' % gap +
            ''.join(f'<span style="display:inline-block;width:{size}px;height:{size}px;border-radius:999px;background:{col(h, l)}"></span>' for h in HUES.values()) + '</div>')


def wordmark(fg, size=27, dot=12, l=0.55, align="flex-end"):
    """The mark, stacked over three lines, the same on every slide. Sized to match the rest of
    the furniture rather than to survive the feed grid: Instagram stamps its carousel badge on
    the top-right corner of every cover, so no mark placed there is readable at grid scale.
    dot tracks size at the proportion the mark has always had (45%), so it scales as a unit."""
    ta = "right" if align == "flex-end" else "center"
    return (f'<div style="display:flex;flex-direction:column;align-items:{align};gap:{int(size*0.5)}px">'
            f'<div class="serif" style="font-size:{size}px;line-height:1.0;letter-spacing:-0.01em;color:{fg};text-align:{ta}">Dinner<br>Table<br>News</div>'
            + dots(dot, int(dot*0.8), l) + '</div>')


def header(fg, l=0.55, left="", top=72, reserve=0):
    """The mark is pinned to the corner, not laid out in the column. It is furniture, like the disc:
    its height must never decide where the copy sits. Laying it out in the flow meant that making the
    mark bigger pushed the text down on every slide at once. `left` (the dateline, the age numeral)
    stays in flow; `reserve` holds the line a slide used to get from the mark itself."""
    mark = f'<div style="position:absolute;top:{top}px;right:72px;z-index:2">{wordmark(fg, l=l)}</div>'
    return mark + (left or f'<div style="height:{reserve}px"></div>')


def dateline(p):
    d = p.get("date") or p.get("slot", "")[:10]
    return date.fromisoformat(d).strftime("%B %-d, %Y")


def chip(kind, h=None, label=""):
    if kind == "shield":
        return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:#E6E1D6;color:{SOFT};font-size:24px;font-weight:500">'
                f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{SOFT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6l7-3z"/></svg>Don\u2019t raise it. If they hear it, say this:</div>')
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:{col(h,0.93,0.045)};color:{col(h)};font-size:24px;font-weight:500">'
            f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{col(h)}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4V5z"/></svg>{label}</div>')


def cover(p):
    """Dateline and wordmark on the top line, then the category and the headline as a narrow sans
    column beside the disc, then the age line, then the kid's question in the big type. Footer: the
    three age chips and the swipe prompt.

    The headline is set in sans at label weight, not in the display serif: it and the question were
    both large white serif, so the eye had to choose between them, and the headline is the one every
    other news account already shows. The question is the promise, so it is the only voice here."""
    photo = p.get("photo")  # path to an image file, optional
    tint = CATS.get(p["category"], CATS["World"])
    cq = p["cover_question"]; h = HUES[cq["band"]]; hc = col(h, 0.72)
    shell = f'position:absolute;top:{DISC_TOP}px;right:{DISC_RIGHT}px;width:{DISC}px;height:{DISC}px;border-radius:999px;background:{tint}'
    if photo:
        # The photo box is exactly the on-slide part of the disc (plus bleed), pinned to the slide's
        # top edge, so the crop comes off the bottom and never off the subject's head. photo_zoom
        # and photo_focus_x are the two tunable knobs; see the photo rule.
        disc = (f'<div style="{shell};overflow:hidden">'
                + photo_img(photo, DISC_W + PHOTO_BLEED, DISC_H, top=-DISC_TOP,
                            zoom=float(p.get("photo_zoom", 1.0)),
                            focus_x=p.get("photo_focus_x", "50%")) + '</div>')
        l = 0.8
    else:
        disc = (f'<div style="{shell}"></div>'
                f'<div style="position:absolute;top:-45px;right:-105px;width:510px;height:510px;border-radius:999px;border:3px solid {INK};opacity:0.5"></div>')
        l = 0.55
    small = 'font-size:22px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:#A8A295'
    left = f'<div style="{small};margin-top:6px">{dateline(p)}</div>'
    age = cover_age(p)
    chips = ''.join(f'<span style="display:inline-flex;align-items:center;padding:12px 22px;border-radius:999px;border:2px solid {col(k,0.72)};color:{col(k,0.72)};font-size:28px;font-weight:500">{LABEL[b_]}</span>' for b_, k in HUES.items())
    return page(INK, PAPER, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{INK};color:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {disc}{header(PAPER if photo else INK, l=l, left=left)}
  <div style="flex:1.2;min-height:96px"></div>
  <div style="position:relative;{small}">{p["category"]}</div>
  <div style="position:relative;margin-top:14px;font-size:38px;font-weight:400;line-height:1.24;letter-spacing:-0.005em;color:#A8A295;max-width:520px;text-wrap:balance">{typo(p["headline"])}</div>
  <div style="position:relative;margin-top:56px;display:flex;align-items:center;gap:16px">
    <div style="width:3px;height:64px;background:{hc};border-radius:2px"></div>
    <div style="font-size:32px;color:#C9C3B5">So your <span style="color:{col(h,0.78)};font-weight:600">{age}-year-old</span> asks</div>
  </div>
  <h1 id="text" class="display" style="position:relative;margin:28px 0 0;font-weight:400;font-size:{QSIZE}px;line-height:0.98;letter-spacing:-0.025em;max-width:940px;text-wrap:balance"><span style="color:{hc}">&ldquo;</span>{typo(cq["q"])}<span style="color:{hc}">&rdquo;</span></h1>
  <div style="flex:1"></div>
  <div style="position:relative;height:1px;background:{hc};opacity:0.28;margin-bottom:34px"></div>
  <div id="floor" style="position:relative;display:flex;justify-content:space-between;align-items:center">
    <div style="display:flex;gap:12px">{chips}</div>
    <div style="font-size:30px;font-weight:500">How to answer, by age &rarr;</div>
  </div>
</div>''')


def age(p, band):
    """Numeral top-left, chip, script, why line, then the tinted "They might ask" band with that age's questions."""
    a = p["ages"][band]; h = HUES[band]; c = col(h); lab = LABEL[band]; qs = p["questions"][band]
    ch = chip("shield") if a.get("shield") else chip("talk", h, typo(a.get("chip", "Bring it up if it fits the day")))
    qa = ''.join(f'<div style="display:flex;flex-direction:column;gap:6px"><div class="serif" style="font-size:38px;line-height:1.15;color:{c}">{typo(q["q"])}</div>'
                 f'<div style="font-size:26px;line-height:1.35;color:{SOFT}">Try: &ldquo;{typo(q["a"])}&rdquo;</div></div>' for q in qs)
    return page(PAPER, INK, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:64px 72px 0;background:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {header(INK, left=f'<div class="serif" style="font-size:96px;line-height:0.8;letter-spacing:-0.04em;color:{c};margin-top:8px">{lab}</div>', top=64)}
  <div style="margin-top:44px;display:flex;flex-direction:column">{ch}</div>
  <div style="margin-top:30px;display:flex;gap:20px;align-items:flex-start">
    <div class="serif" style="font-size:140px;line-height:0.6;color:{c};margin-top:30px">&ldquo;</div>
    <p class="serif" style="margin:0;font-size:46px;line-height:1.28;letter-spacing:-0.01em;text-wrap:pretty">{typo(a["script"])}</p>
  </div>
  <div id="text" style="margin-top:30px;padding-left:78px;max-width:900px;font-size:26px;line-height:1.4;color:{SOFT};text-wrap:pretty"><span style="font-weight:600;letter-spacing:0.06em;text-transform:uppercase;font-size:19px;color:{c}">Why it works</span><br>{typo(a["why"])}</div>
  <div style="flex-grow:1;min-height:{MIN_GAP}px"></div>
  <div id="floor" style="margin:0 -72px;padding:40px 72px 44px;background:{col(h,0.93,0.045)};display:flex;flex-direction:column;gap:22px">
    <div style="font-size:20px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{c}">They might ask</div>
    {qa}
    <div style="margin-top:6px;display:flex;justify-content:space-between;font-size:24px;font-weight:500;color:{c}"><span>Save this for dinner</span><span>{NEXT[band]}</span></div>
  </div>
</div>''')


def table(p):
    """Closing slide: one question anyone at the table can answer, the comment ask, then save / send / follow."""
    return page(INK, PAPER, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{INK};color:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {header(PAPER, l=0.8, reserve=33)}
  <div style="flex-grow:0.6"></div>
  <div style="font-size:26px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;color:#A8A295">The dinner table question</div>
  <h2 class="display" style="margin:28px 0 0;font-weight:400;font-size:92px;line-height:1.04;letter-spacing:-0.02em;max-width:920px;text-wrap:balance">{typo(p["table_question"])}</h2>
  <p id="text" style="margin:44px 0 0;font-size:34px;line-height:1.4;color:#C9C3B5;max-width:840px">Ask it at any age. Tell us what your kid said in the comments.</p>
  <div style="flex-grow:1"></div>
  <div id="floor" style="display:flex;justify-content:space-between;align-items:flex-end;font-size:30px;color:#C9C3B5">
    <div><span style="color:{PAPER};font-weight:500">Save</span> this one for dinner.<br><span style="color:{PAPER};font-weight:500">Send</span> it to another parent.<br><span style="color:{PAPER};font-weight:500">Follow</span> for today\u2019s news, explained for your kid\u2019s age.</div>{dots(16, 12, 0.65)}
  </div>
</div>''')


def swipe_line(a):
    """"at age 6" on the first one and bare numbers after it. Spelling out "age" three times reads
    like a form, and leaving it off entirely makes the first number look like a time."""
    return f"Swipe for what to say at age {a['5-7']}, at {a['8-12']}, and at {a['13-17']}."


def age_blocks(p):
    """The three scripts, each under the age the post drew for its band. "At age 6" on the first one
    and bare numbers after it: spelling out "age" three times reads like a form, and leaving it off
    the first makes the number look like a time."""
    a = ages_named(p)
    label = [f"At age {a['5-7']}", f"At {a['8-12']}", f"At {a['13-17']}"]
    return [f'{l}: {p["ages"][b]["script"]}' for l, b in zip(label, ("5-7", "8-12", "13-17"))]


def why_block(p):
    band = p["cover_question"]["band"]
    a = p["ages"][band]
    return f'Why this works at age {ages_named(p)[band]}: {a.get("why_long") or a["why"]}'


def build_caption(p, reel=False):
    """The Instagram caption, in the standard order. The first line answers the cover question, so in the
    feed the cover asks and the caption answers; the table question is the last thing before the hashtags.

    The source line is the outlet and nothing else. The domain repeated the outlet in smaller type,
    which is the call site.py already made for the cards on the website.

    reel=True swaps the swipe line for the thing it promises. A reel plays one age and says the other
    two are down here, so the caption carries all three scripts and the why for the age that played.
    It also drops the photo credit: the reel shows the headline as a clipping and no photograph, so
    crediting one is crediting a picture nobody saw."""
    credit = f'\n{p["photo_credit"]}' if p.get("photo") and p.get("photo_credit") and not reel else ""
    source = f'Source: {p["outlet"]}' + credit
    middle = age_blocks(p) + [why_block(p)] if reel else [swipe_line(ages_named(p))]
    parts = [p["cover_answer"], p["summary"], source] + middle + [
        f'The dinner table question: {p["table_question"]} Tell us what your kid said, and how old they are.',
        " ".join(p["hashtags"])]
    return "\n\n".join(parts)


def check_composite(p):
    """Return a PHOTO message if the Commons file is a stacked composite and no photo_zoom has been
    recorded. Two photographs in one disc reads as a doubled picture, and it shipped once that way
    (2026-09-19-morning, White_House_north_and_south_sides.jpg). Setting photo_zoom is the run
    saying it looked: any value clears this, including 1.0 when the composite happens to frame well."""
    credit = composite_source(p)
    if credit and "photo_zoom" not in p:
        return (f"PHOTO: the Commons file is a stacked composite (artist: {credit}). At photo_zoom 1.0 the disc "
                f"shows both photographs at once. Look at the cover, set \"photo_zoom\" in post.json to frame one "
                f"of them (about 2.1 for a half-and-half stack), and re-render. Set it to 1.0 if it reads fine.")
    return None


def check_hashtags(p):
    """Return a HASHTAGS message if the tag list breaks the rule, else None. Four tags, fixed at both
    ends, with exactly one tag in the middle that names what this story is about. The middle one is
    where generic category labels kept creeping in: #Economy on a Government story says nothing."""
    tags = p.get("hashtags", [])
    shape = f"{SWIPE_TAGS[0]}, {SWIPE_TAGS[1]}, <one story tag>, {BRAND_TAG}"
    if len(tags) != 4:
        return f"HASHTAGS: {len(tags)} tags, must be exactly 4 — {shape}. Got: {' '.join(tags) or '(none)'}"
    if list(tags[:2]) != SWIPE_TAGS or tags[-1] != BRAND_TAG:
        return f"HASHTAGS: the list must read {shape}. Got: {' '.join(tags)}"
    story = tags[2]
    if story.lstrip("#").replace(" ", "").lower() in GENERIC_TAGS:
        return (f"HASHTAGS: {story} is a category label, not a story tag. Use what the story is actually "
                f"about — a name, place, bill, company, event — not the section it files under.")
    if story in SWIPE_TAGS or story == BRAND_TAG:
        return f"HASHTAGS: {story} is already a fixed tag; the third slot is the story tag."
    return None


def check_photo(pg):
    """Return a PHOTO message if the cover photo leaves bare tint on the slide or is anchored anywhere
    but the top of its frame, else None. Measures what actually rendered, not what we meant to write."""
    r = pg.evaluate("(() => { const i = document.getElementById('photo'); if (!i) return null;"
                    " const b = i.getBoundingClientRect();"
                    " return [b.top, b.right, b.bottom, getComputedStyle(i).objectPosition]; })()")
    if not r: return None                      # no photo on this cover
    top, right, bottom, pos = r
    if top > 0.5 or right < 1080 - 0.5 or bottom < DISC_H - 0.5:
        short = max(top, 1080 - right, DISC_H - bottom)
        return (f"PHOTO: the photo misses the on-slide part of the disc by {short:.0f}px, so a strip of bare "
                f"category tint shows at its edge. The photo box must cover 0,0 to 1080,{DISC_H}.")
    if not pos.split()[-1].startswith("0"):
        return (f"PHOTO: object-position is '{pos}'. The vertical anchor must stay at the top (0%) so the "
                f"crop comes off the bottom of the frame and never off the subject's head.")
    return None


def check(pg, name):
    """Return a TOO LOW message if #text sits too close to #floor or #floor runs off the slide, else None."""
    if name == "1-cover":
        msg = check_photo(pg)
        if msg: return msg
    gap, bottom = pg.evaluate("(() => { const t = document.getElementById('text').getBoundingClientRect(), f = document.getElementById('floor').getBoundingClientRect();"
                              " return [f.top - t.bottom, f.bottom]; })()")
    what = {"1-cover": "the question", "5-table": "the question or the comment line"}.get(name, "the script, the why line, or a Try answer")
    if bottom > 1350 + 0.5:
        return f"TOO LOW: {name}: the bottom block runs {bottom - 1350:.0f}px past the end of the slide. Shorten {what} and re-render."
    if gap < GAP[name] - 0.5:
        return f"TOO LOW: {name}: only {gap:.0f}px of space above the bottom block (minimum {GAP[name]}). Shorten {what} and re-render."
    return None


def render(post, outdir, post_path=None):
    for k in ("date", "cover_question", "cover_answer", "table_question", "source_domain", "hashtags"):
        if k not in post: raise SystemExit(f"post.json is missing '{k}' (see posts/samples-v2-2026-09-13-evening/post.json)")
    drew = "ages_named" not in post
    post["ages_named"] = ages_named(post)   # drawn here so the caption and the cover name one kid
    slides = [("1-cover", cover(post)), ("2-ages-5-7", age(post, "5-7")), ("3-ages-8-12", age(post, "8-12")),
              ("4-ages-13-17", age(post, "13-17")), ("5-table", table(post))]
    os.makedirs(outdir, exist_ok=True); problems = []
    for msg in (check_composite(post), check_hashtags(post)):
        if msg: problems.append(msg)
    caption = build_caption(post)
    if post_path and (drew or not post.get("caption")):  # write the drawn ages, and the caption on a first render
        post.setdefault("caption", caption)
        json.dump(post, open(post_path, "w"), indent=2, ensure_ascii=False); open(post_path, "a").write("\n")
        print(f"ages and caption written to {post_path}", file=sys.stderr)
    elif post.get("caption") != caption:
        problems.append("CAPTION: post.json's caption is not the standard caption built from its fields. Delete the caption "
                        "field and re-render, or replace it with:\n" + caption)
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception:  # pip's playwright may pin a different revision than the preinstalled browser
            import glob
            exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") + ["/opt/pw-browsers/chromium"])[0]
            b = pw.chromium.launch(executable_path=exe)
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        for name, html in slides:
            pg.set_content(html); pg.wait_for_timeout(150)
            pg.screenshot(path=os.path.join(outdir, f"{name}.jpg"), type="jpeg", quality=92)
            msg = check(pg, name)
            if msg: problems.append(msg)
        b.close()
    return [os.path.join(outdir, f"{n}.jpg") for n, _ in slides], problems


if __name__ == "__main__":
    post = json.load(open(sys.argv[1]))
    files, problems = render(post, sys.argv[2], post_path=sys.argv[1])
    for f in files: print(f)
    for m in problems: print(m, file=sys.stderr)
    sys.exit(1 if problems else 0)
