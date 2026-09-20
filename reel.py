#!/usr/bin/env python3
"""Render a Dinner Table News post to a vertical reel (1080x1920) and its cover.

usage: python reel.py posts/<slug>/post.json posts/<slug>/
writes: reel.mp4 (~14s, H.264 + silent AAC), reel-cover.jpg, reel-caption.txt

Three beats on one screen: the headline as a newspaper clipping, the question a kid that age asks,
the line a parent says back, and the ask to save it. The clipping is pinned to the same pixel on
every frame, so the only thing that ever changes is the block underneath it. That is what makes the
reel loop: a viewer who watches twice sees the text under the clipping reset, not a cut back to a
title card, and the four seconds the old format spent building a headline they had already read are
gone. Fourteen seconds is also the whole reel inside one replay of most audio hooks.

One age, not three. The first cut played 5, 10 and 15 in turn and lost a third of its viewers at
second six: it opened on the teenager's question and then abandoned it to answer the five-year-old's.
The other two ages live in the caption, which is what the last beat sends people to.

Frames come from the same HTML, CSS and fonts as render.py, stepped at an explicit time and
screenshotted, so a reel is reproducible and the two formats can never drift apart visually.

Safe zones (measured off live screenshots, not assumed). Instagram's own chrome — status bar, back
arrow, "Reels" title, right-hand icon — covers video y 0..250, so TOP clears it. The like/comment/
share rail sits right of x~900 over the lower half, so readable text is capped at MAX_W. The
username, caption and audio row occupies roughly y 1700..1900, so BOTTOM stays clear of it.

The profile grid is a third safe zone and the one that caught us: it keeps only the 4:5 band from
y 285 to 1635 of the cover. At TOP 285 the wordmark sat exactly on that line and the grid sliced the
top off "Dinner", so TOP now leaves it 55px of headroom inside the crop.

Timing is a reading rate, not a taste: WPS words a second plus LEAD for finding the line. The save
beat runs at WPS_SIGN, because a sign-off is read at a glance rather than studied.

Audio is a silent stereo AAC track: Instagram wants an audio stream, and the music is chosen by
hand in the app at post time. Do not bake in a track without a licence that covers it.
"""
import json, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render
from render import PAPER, INK, HUES, col, page, typo, ages_named, cover_age, dateline, wordmark
from playwright.sync_api import sync_playwright

W, H = 1080, 1920
PAD_X, TOP, BOTTOM = 96, 340, 400            # TOP also clears CROP_TOP: see below
CROP_TOP, CROP_BOT = 285, 1635               # the 4:5 band the profile grid keeps from a 9:16 cover
MAX_W = 780                                  # readable measure: clears the right-hand button rail
FPS = 30
WPS, LEAD = 3.5, 0.8                         # ~210 wpm, plus time to find the line
WPS_SIGN = 4.0                               # the save line is a sign-off, not something to study
SLOT = 370                                   # the block under the clipping, fixed so it cannot move
QUESTION_SIZES = [104, 94, 86, 78]
ANSWER_SIZES = [80, 72, 66, 60]
NEWSPRINT = "#EFECE3"
EYE = "font-size:30px;font-weight:500;letter-spacing:.09em;text-transform:uppercase"
SAVE_SIZE = 64
SAVE_LINE = "Save this for tonight’s dinner table."
CAPTION_LINE = "More for all kids age 5-17 in the caption."
CAP_LIMIT = 2200                             # Instagram truncates past this

# Instagram's own bookmark, set inline at the head of the sentence so a second line starts at the
# left margin with the line under it instead of hanging off a flex row.
SAVE = (f"<svg width='{SAVE_SIZE * 0.84:.0f}' height='{SAVE_SIZE * 0.84:.0f}' viewBox='0 0 24 24' fill='none' "
        "stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' "
        f"style='vertical-align:{-SAVE_SIZE * 0.17:.0f}px'>"
        "<path d='M6 3h12a1 1 0 0 1 1 1v17l-7-5-7 5V4a1 1 0 0 1 1-1z'/></svg>")

# The headline as a piece of newsprint: rules over the kick, a serif head, a byline, two justified
# columns fading out under it. Paper on an ink background says "this is the news" without a caption
# saying so, and the half-degree rotation is what stops it reading as another slide.
CLIPPING_CSS = f"""<style>
.clip{{background:{NEWSPRINT};color:#1B1A17;padding:26px 30px 0;width:{MAX_W}px;
  transform:rotate(-0.45deg);box-shadow:0 14px 30px rgba(0,0,0,.5);overflow:hidden}}
.clip .rule{{height:5px;background:#1B1A17}}
.clip .rule.thin{{height:1px;margin-top:5px}}
.clip .kick{{font-family:'Instrument Sans',sans-serif;font-size:21px;font-weight:600;
  letter-spacing:.18em;text-transform:uppercase;color:#3D3A34;margin-top:16px}}
.clip .head{{font-family:'Libre Caslon Text',Georgia,serif;font-weight:700;font-size:64px;
  line-height:1.1;letter-spacing:-.015em;margin-top:12px;text-wrap:balance}}
.clip .hr{{height:1px;background:#8C867A;margin-top:20px}}
.clip .by{{font-family:'Instrument Sans',sans-serif;font-size:20px;color:#6B675F;margin-top:12px}}
.clip .cols{{column-count:2;column-gap:28px;font-family:'Libre Caslon Text',Georgia,serif;
  font-size:19px;line-height:1.42;color:#3D3A34;text-align:justify;margin-top:14px;height:118px;
  -webkit-mask-image:linear-gradient(to bottom,#000 46%,transparent 96%);
  mask-image:linear-gradient(to bottom,#000 46%,transparent 96%)}}
</style>"""


def words(*parts):
    return sum(len(re.findall(r"\S+", s)) for s in parts)


def ease(t, start, dur=0.45, rise=24):
    """Fade up and settle. Cubic ease-out, no scale, no bounce: the type should look like it is
    setting on the page, not animating."""
    p = 0.0 if t <= start else 1.0 if t >= start + dur else (t - start) / dur
    p = 1 - (1 - p) ** 3
    return f"opacity:{p:.3f};transform:translateY({(1 - p) * rise:.2f}px)"


def browser(pw):
    try:
        return pw.chromium.launch()
    except Exception:  # pip's playwright may pin a different revision than the preinstalled browser
        import glob
        exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") + ["/opt/pw-browsers/chromium"])[0]
        return pw.chromium.launch(executable_path=exe)


def frame(p, body):
    """Everything above the slot is fixed and identical on every beat. The slot is a set height
    rather than a minimum: let it grow and a long answer pushes the clipping up, the loop point
    becomes a jump, and the reel stops being one continuous shot."""
    return page(INK, PAPER, CLIPPING_CSS + f'''<div style="width:{W}px;height:{H}px;box-sizing:border-box;
      padding:{TOP}px {PAD_X}px {BOTTOM}px;background:{INK};color:{PAPER};display:flex;flex-direction:column;
      position:relative;overflow:hidden">
  <div style="display:flex;justify-content:flex-end">{wordmark(PAPER, l=0.8)}</div>
  <div style="flex:0.55"></div>
  <div style="{EYE};color:#A8A295">Today&rsquo;s headline says</div>
  <div style="margin-top:20px">
    <div class="clip">
      <div class="rule"></div><div class="rule thin"></div>
      <div class="kick">{p["category"]}</div>
      <div class="head">{typo(p["headline"])}</div>
      <div class="hr"></div>
      <div class="by">By {p["outlet"]} &middot; {dateline(p)}</div>
      <div class="cols">{typo(p["summary"])}</div>
    </div></div>
  <div style="margin-top:68px;height:{SLOT}px;overflow:hidden"><div id="slot">{body}</div></div>
  <div style="flex:0.45"></div>
</div>''')


def beat_question(p, hc, age, t, size=QUESTION_SIZES[0]):
    """The headline is already on screen at t=0. The age line lands, then the question right behind
    it. The gap between them is the beat where a parent recognises their own kid."""
    return frame(p, f'''
  <div style="{ease(t, 1.60)};font-size:38px;color:#C9C3B5">And your <span style="color:{hc};font-weight:600">{age}-year-old</span> asks</div>
  <div class="display" style="{ease(t, 2.00, 0.55, 30)};margin-top:24px;font-size:{size}px;line-height:1.0;
       letter-spacing:-.025em;max-width:{MAX_W}px;text-wrap:balance">
    <span style="color:{hc}">&ldquo;</span>{typo(p["cover_question"]["q"])}<span style="color:{hc}">&rdquo;</span></div>''')


def beat_answer(p, hc, age, t, size=ANSWER_SIZES[0]):
    return frame(p, f'''
  <div style="{ease(t, 0.0)};{EYE};color:{hc}">Try saying</div>
  <div class="serif" style="{ease(t, 0.25, 0.55, 30)};margin-top:26px;font-size:{size}px;line-height:1.2;
       letter-spacing:-.01em;max-width:{MAX_W}px;text-wrap:pretty;border-left:5px solid {hc};padding-left:28px">{typo(p["cover_answer"])}</div>''')


def beat_save(p, hc, age, t, size=None):
    """Save, not follow. A stranger will bookmark something they can picture needing tonight long
    before they will follow an account they have seen once, and the line has to name the occasion
    or "tonight" is just a time."""
    return frame(p, f'''
  <div style="{ease(t, 0.0, 0.5, 26)};color:{hc};font-size:{SAVE_SIZE}px;font-weight:600;letter-spacing:-.01em;
       line-height:1.2;max-width:{MAX_W}px;text-wrap:balance">{SAVE}&nbsp;{SAVE_LINE}</div>
  <div style="{ease(t, 0.35, 0.5, 22)};margin-top:26px;font-size:40px;line-height:1.35;color:#C9C3B5;max-width:{MAX_W}px">
    {CAPTION_LINE}</div>''')


def fit(pg, beat, post, hc, age, sizes, what):
    """Largest size that keeps the block inside the slot. Measured in the browser, not estimated
    from a character count, so it cannot drift from what renders."""
    for size in sizes:
        pg.set_content(beat(post, hc, age, 99, size)); pg.wait_for_timeout(30)
        if pg.evaluate("() => document.getElementById('slot').getBoundingClientRect().height") <= SLOT:
            return size
    raise SystemExit(f"REEL: the {what} does not fit the slot under the clipping even at {sizes[-1]}px. "
                     f"Shorten it in post.json and run again.")


def render_reel(post, outdir):
    # Pin the ages before the first frame. cover_age() draws when post.json has none, and drawn
    # per frame it would count the kid up and down through the beat.
    post["ages_named"] = ages_named(post)
    band = post["cover_question"]["band"]
    hc, age = col(HUES[band], 0.78), cover_age(post)
    frames = os.path.join(outdir, ".frames"); os.makedirs(frames, exist_ok=True)
    n = 0
    with sync_playwright() as pw:
        b = browser(pw)
        pg = b.new_page(viewport={"width": W, "height": H})
        qs = fit(pg, beat_question, post, hc, age, QUESTION_SIZES, "cover question")
        as_ = fit(pg, beat_answer, post, hc, age, ANSWER_SIZES, "cover answer")
        # The question beat holds from when the question lands, not from zero: 2.55s of staging,
        # then the words, then a breath.
        beats = [(lambda t: beat_question(post, hc, age, t, qs),
                  2.55 + words(post["cover_question"]["q"]) / WPS + 0.9),
                 (lambda t: beat_answer(post, hc, age, t, as_),
                  LEAD + words("Try saying", post["cover_answer"]) / WPS),
                 (lambda t: beat_save(post, hc, age, t),
                  LEAD + words(SAVE_LINE, CAPTION_LINE) / WPS_SIGN)]
        for beat, dur in beats:
            for k in range(int(round(dur * FPS))):
                pg.set_content(beat(k / FPS)); pg.wait_for_timeout(15)
                pg.screenshot(path=os.path.join(frames, f"{n:05d}.png"), type="png"); n += 1
        # The cover is the question beat, fully landed. It shares no composition with the carousel
        # cover on purpose: the two sit next to each other in the profile grid, and a reel that
        # looks like the carousel reads as the same story posted twice.
        pg.set_content(beat_question(post, hc, age, 99, qs)); pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(outdir, "reel-cover.jpg"), type="jpeg", quality=94)
        b.close()

    total = n / FPS
    bed = os.path.join(frames, "bed.m4a")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate=44100:d={total}",
                    "-c:a", "aac", "-b:a", "128k", bed], check=True, capture_output=True)
    out = os.path.join(outdir, "reel.mp4")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "%05d.png"),
                    "-i", bed, "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", "-shortest", out], check=True, capture_output=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))
    os.rmdir(frames)
    caption = render.build_caption(post, reel=True)
    if len(caption) > CAP_LIMIT:
        raise SystemExit(f"REEL: the caption is {len(caption)} characters against Instagram's {CAP_LIMIT}. "
                         f"Cut {len(caption) - CAP_LIMIT} from the scripts or the why in post.json.")
    cap = os.path.join(outdir, "reel-caption.txt")
    open(cap, "w").write(caption + "\n")
    return out, os.path.join(outdir, "reel-cover.jpg"), cap, total


if __name__ == "__main__":
    post = json.load(open(sys.argv[1]))
    mp4, jpg, cap, secs = render_reel(post, sys.argv[2])
    print(mp4); print(jpg); print(cap); print(f"{secs:.1f}s", file=sys.stderr)
