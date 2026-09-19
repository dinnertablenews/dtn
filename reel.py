#!/usr/bin/env python3
"""Render a Dinner Table News post to a vertical reel (1080x1920) and its cover.

usage: python reel.py posts/<slug>/post.json posts/<slug>/
writes: reel.mp4 (20.5s, H.264 + silent AAC), reel-cover.jpg, reel-caption.txt

The reel is not the carousel. It is the promise in five beats: the kid's question, then the one line
a parent says at 5, at 10 and at 15, then the table question. The per-age lines are the "Try:"
answers already in post.json — short, already written, already the words a parent says — so a reel
needs no new copy and no new fields.

Frames come from the same HTML, CSS and fonts as render.py, stepped at an explicit time and
screenshotted, so a reel is reproducible and the two formats can never drift apart visually.

Safe zones (measured off live screenshots, not assumed). Instagram's own chrome — status bar, back
arrow, "Reels" title, right-hand icon — covers video y 0..250, so TOP clears it. The like/comment/
share rail sits right of x~900 over the lower half, so readable text is capped at MAX_W. The
username, caption and audio row occupies roughly y 1700..1900, so BOTTOM stays clear of it.

Audio is a silent stereo AAC track: Instagram wants an audio stream, and the music is chosen by
hand in the app at post time. Do not bake in a track without a licence that covers it.
"""
import json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import base64
import render
from render import PAPER, INK, SOFT, HUES, col, dots, page, typo, cover_age, wordmark
from playwright.sync_api import sync_playwright

W, H = 1080, 1920
PAD_X, TOP, BOTTOM = 96, 285, 400
MAX_W = 780                                  # readable measure: clears the right-hand button rail
BEATS = [3.5, 5.0, 4.5, 5.0, 2.5]            # 20.5s
ANSWER_SIZES = [86, 78, 70, 64, 58]          # the age answer steps down until it clears the dots
MIN_GAP = 48                                 # px between the answer and the progress dots
FPS = 30
AGE_AT = {"5-7": "5", "8-12": "10", "13-17": "15"}
CROP_TOP, CROP_BOT = 285, 1635               # the ~4:5 band the profile grid keeps from a 9:16 cover
DISC_Y = CROP_TOP + render.DISC_TOP          # the carousel's disc position, measured inside that band
HEAD_W = 520                                 # headline measure on the hook: clears the disc, as on the cover


def shell(body, bg=INK, fg=PAPER, top=TOP, bottom=BOTTOM):
    return page(bg, fg, f'<div style="width:{W}px;height:{H}px;box-sizing:border-box;'
                        f'padding:{top}px {PAD_X}px {bottom}px;background:{bg};color:{fg};'
                        f'display:flex;flex-direction:column;position:relative;overflow:hidden">{body}</div>')


def header(fg, l):
    """z-index puts the mark above the disc: the disc is absolutely positioned, so without a stacking
    context of its own an ordinary flow header paints underneath it and the mark disappears."""
    return f'<div style="position:relative;z-index:2;display:flex;justify-content:flex-end">{wordmark(fg, l=l)}</div>'


def ease(t, start, dur=0.45, rise=24):
    """Fade up and settle. Cubic ease-out, no scale, no bounce: the type should look like it is
    setting on the page, not animating."""
    p = 0.0 if t <= start else 1.0 if t >= start + dur else (t - start) / dur
    p = 1 - (1 - p) ** 3
    return f"opacity:{p:.3f};transform:translateY({(1 - p) * rise:.2f}px)"


def progress(i):
    """Three dots, the current one filled. It tells a viewer at second four that there are three
    ages coming, which is the reason to stay past the hook."""
    out = []
    for k, hue in enumerate(HUES.values()):
        on = k == i
        out.append(f'<span style="display:inline-block;width:{22 if on else 14}px;height:14px;'
                   f'border-radius:999px;background:{col(hue, 0.72) if on else "#00000022"}"></span>')
    return f'<div style="display:flex;align-items:center;gap:12px">{"".join(out)}</div>'


def disc(p):
    """The cover disc, sitting where it sits on the carousel cover. The grid crop of a reel cover is
    exactly 1080x1350 — a carousel cover's dimensions — so placing it at CROP_TOP + DISC_TOP makes the
    two read as the same object in the profile grid.

    The photo fills the whole on-frame part of the circle. On the carousel the disc hangs off the top
    of the slide and the photo only has to fill the lower DISC_H; here the disc's top edge is inside
    the frame, so a photo sized that way leaves a band of bare tint under the picture. Height is the
    full disc. Width stays the on-frame width: the rest of the circle is off the right edge, and
    keeping the photo narrow is what holds the subject in the part a viewer can see.

    The box is taller here than on the carousel cover, which is where a stacked Commons composite
    shows up worst: at photo_zoom 1.0 the whole of both photographs fits in and the disc reads
    doubled. photo_zoom is shared with the cover so one value frames both."""
    tint = render.CATS.get(p["category"], render.CATS["World"])
    D, R = render.DISC, render.DISC_RIGHT
    shell_css = (f'position:absolute;top:{DISC_Y}px;right:{R}px;width:{D}px;height:{D}px;'
                 f'border-radius:999px;background:{tint}')
    ph = p.get("photo")
    if not ph:
        return (f'<div style="{shell_css}"></div>'
                f'<div style="position:absolute;top:{CROP_TOP - 45}px;right:-105px;width:510px;height:510px;'
                f'border-radius:999px;border:3px solid {INK};opacity:0.5"></div>')
    return (f'<div style="{shell_css};overflow:hidden">'
            + render.photo_img(ph, render.DISC_W + render.PHOTO_BLEED, D, top=0,
                               zoom=float(p.get("photo_zoom", 1.0)),
                               focus_x=p.get("photo_focus_x", "50%")) + '</div>')


def hook_body(p, t):
    cq = p["cover_question"]; h = HUES[cq["band"]]; hc = col(h, 0.72)
    return f'''
  {disc(p)}{header(PAPER, 0.8)}
  <div style="flex:1"></div>
  <div style="{ease(t, 0.00)};font-size:28px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:#A8A295;position:relative">{p["category"]}</div>
  <div style="{ease(t, 0.10)};margin-top:16px;font-size:44px;line-height:1.24;color:#A8A295;max-width:{HEAD_W}px;position:relative;text-wrap:balance">{typo(p["headline"])}</div>
  <div style="{ease(t, 0.60)};margin-top:56px;font-size:38px;color:#C9C3B5">So your <span style="color:{col(h,0.78)};font-weight:600">{cover_age(p)}-year-old</span> asks</div>
  <div class="display" style="{ease(t, 1.05, 0.55, 30)};margin-top:26px;font-size:140px;line-height:0.96;letter-spacing:-0.025em;max-width:{MAX_W}px;text-wrap:balance">
    <span style="color:{hc}">&ldquo;</span>{typo(cq["q"])}<span style="color:{hc}">&rdquo;</span></div>
  <div style="flex:1.05"></div>'''


def hook(p, t=99.0):
    return shell(hook_body(p, t))


def age_beat(p, band, i, t=99.0, size=ANSWER_SIZES[0]):
    """The answer is existing carousel copy and runs from 80 to 158 characters across the corpus, so
    unlike a slide it cannot be fixed by shortening the text: the same words also have to serve the
    age card. The type steps down instead. The three beats are sequential rather than side by side,
    so they do not have to match each other the way the three age cards do."""
    c = col(HUES[band], 0.55); q = p["questions"][band][0]
    return shell(f'''
  <div class="serif" style="{ease(t, 0.00, 0.35)};font-size:150px;line-height:0.78;letter-spacing:-0.04em;color:{c}">At {AGE_AT[band]}</div>
  <div style="{ease(t, 0.12, 0.35)};margin-top:56px;font-size:36px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;color:{c}">They ask</div>
  <div class="serif" style="{ease(t, 0.20, 0.35)};margin-top:14px;font-size:56px;line-height:1.2;color:{SOFT};max-width:{MAX_W}px">{typo(q["q"])}</div>
  <div style="{ease(t, 0.34, 0.3)};margin-top:64px;width:86px;height:4px;background:{c};border-radius:2px"></div>
  <div id="answer" class="serif" style="{ease(t, 0.45, 0.5, 30)};margin-top:44px;font-size:{size}px;line-height:1.2;letter-spacing:-0.01em;max-width:{MAX_W}px;text-wrap:pretty">{typo(q["a"])}</div>
  <div style="flex:1"></div>
  <div id="dots" style="margin-bottom:40px">{progress(i)}</div>''', bg=PAPER, fg=INK)


def close(p, t=99.0):
    return shell(f'''
  {header(PAPER, 0.8)}
  <div style="flex:1"></div>
  <div style="{ease(t, 0.00, 0.4)};font-size:30px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;color:#A8A295">The dinner table question</div>
  <div class="display" style="{ease(t, 0.12, 0.5, 30)};margin-top:28px;font-size:104px;line-height:1.04;letter-spacing:-0.02em;max-width:{MAX_W}px;text-wrap:balance">{typo(p["table_question"])}</div>
  <div style="flex:1"></div>
  <div style="{ease(t, 0.70, 0.45)};font-size:40px;line-height:1.35;color:#C9C3B5"><span style="color:{PAPER};font-weight:500">Follow</span> for today’s news,<br>explained for your kid’s age.</div>''')


def cover(p):
    """The settled hook, composed inside the band the profile grid keeps. A reel lands in the main
    grid as well as the Reels tab, and the main grid crops a 9:16 cover to about 4:5, so the mark
    and the question both have to sit inside CROP_TOP..CROP_BOT."""
    return shell(hook_body(p, 99.0), top=CROP_TOP + 40, bottom=H - CROP_BOT + 40)


def browser(pw):
    try:
        return pw.chromium.launch()
    except Exception:  # pip's playwright may pin a different revision than the preinstalled browser
        import glob
        exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") + ["/opt/pw-browsers/chromium"])[0]
        return pw.chromium.launch(executable_path=exe)


def fit_answer(pg, post, band, i):
    """Largest size in ANSWER_SIZES that leaves MIN_GAP between the answer and the dots. Measured in
    the browser, not estimated from a character count, so it cannot drift from what renders."""
    for size in ANSWER_SIZES:
        pg.set_content(age_beat(post, band, i, size=size)); pg.wait_for_timeout(30)
        gap = pg.evaluate("() => document.getElementById('dots').getBoundingClientRect().top"
                          " - document.getElementById('answer').getBoundingClientRect().bottom")
        if gap >= MIN_GAP:
            return size
    return None


def render_reel(post, outdir):
    frames = os.path.join(outdir, ".frames"); os.makedirs(frames, exist_ok=True)
    n = 0
    with sync_playwright() as pw:
        b = browser(pw)
        pg = b.new_page(viewport={"width": W, "height": H})
        sizes = {}
        for i, band in enumerate(("5-7", "8-12", "13-17")):
            sizes[band] = fit_answer(pg, post, band, i)
            if sizes[band] is None:
                b.close()
                raise SystemExit(f"REEL: the {band} answer does not fit above the progress dots even at "
                                 f"{ANSWER_SIZES[-1]}px. Shorten that Try answer in post.json.")
        beats = [lambda t: hook(post, t),
                 lambda t: age_beat(post, "5-7", 0, t, sizes["5-7"]),
                 lambda t: age_beat(post, "8-12", 1, t, sizes["8-12"]),
                 lambda t: age_beat(post, "13-17", 2, t, sizes["13-17"]),
                 lambda t: close(post, t)]
        for beat, dur in zip(beats, BEATS):
            for k in range(int(round(dur * FPS))):
                pg.set_content(beat(k / FPS)); pg.wait_for_timeout(15)
                pg.screenshot(path=os.path.join(frames, f"{n:05d}.png"), type="png"); n += 1
        pg.set_content(cover(post)); pg.wait_for_timeout(200)
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
    cap = os.path.join(outdir, "reel-caption.txt")
    open(cap, "w").write(render.build_caption(post, reel=True) + "\n")
    return out, os.path.join(outdir, "reel-cover.jpg"), cap, total


if __name__ == "__main__":
    post = json.load(open(sys.argv[1]))
    mp4, jpg, cap, secs = render_reel(post, sys.argv[2])
    print(mp4); print(jpg); print(cap); print(f"{secs:.1f}s", file=sys.stderr)
