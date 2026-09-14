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
"""
import base64, json, os, sys
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
MIN_GAP = 72            # age cards: paper between the why line and the band
GAP = {"1-cover": 45, "2-ages-5-7": MIN_GAP, "3-ages-8-12": MIN_GAP, "4-ages-13-17": MIN_GAP, "5-table": 45}
def col(h, l=0.55, c=0.13): return f"oklch({l} {c} {h})"


def prepare_photo(path, scale=0.66):
    """Pad the photo with white so it lands in the visible lower-left of the disc.
    White multiplies to the category tint, so the padding disappears. scale = photo width / disc width."""
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    W = int(im.width / scale); H = max(int(W * 1.3), im.height)  # canvas taller than wide, like the disc's cover box
    canvas = Image.new("RGB", (W, H), "white"); canvas.paste(im, (0, H - im.height))
    buf = io.BytesIO(); canvas.save(buf, "JPEG", quality=88); return buf.getvalue()


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


def wordmark(fg, size=20, dot=9, l=0.55, align="flex-end"):
    ta = "right" if align == "flex-end" else "center"
    return (f'<div style="display:flex;flex-direction:column;align-items:{align};gap:{int(size*0.5)}px">'
            f'<div class="serif" style="font-size:{size}px;line-height:1.0;letter-spacing:-0.01em;color:{fg};text-align:{ta}">Dinner<br>Table<br>News</div>'
            + dots(dot, int(dot*0.8), l) + '</div>')


def header(fg, l=0.55, left=""):
    return f'<div style="position:relative;display:flex;justify-content:{"space-between" if left else "flex-end"};align-items:flex-start">{left}{wordmark(fg, l=l)}</div>'


def dateline(p):
    d = p.get("date") or p.get("slot", "")[:10]
    return date.fromisoformat(d).strftime("%B %-d, %Y")


def chip(kind, h=None, label=""):
    if kind == "shield":
        return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:#E6E1D6;color:{SOFT};font-size:24px;font-weight:500">'
                f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{SOFT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6l7-3z"/></svg>Don\'t raise it. If they hear it, say this:</div>')
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:{col(h,0.93,0.045)};color:{col(h)};font-size:24px;font-weight:500">'
            f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{col(h)}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4V5z"/></svg>{label}</div>')


def cover(p):
    """Dateline top-left, wordmark top-right, category, the headline, then the kid's question in the big type,
    tagged with the age bracket it comes from. Footer: the three age chips and the swipe prompt."""
    photo = p.get("photo")  # path to an image file, optional
    tint = CATS.get(p["category"], CATS["World"])
    cq = p["cover_question"]; h = HUES[cq["band"]]; hc = col(h, 0.72)
    if photo:
        b = base64.b64encode(prepare_photo(photo, p.get("photo_scale", 0.66))).decode()
        disc = (f'<div style="position:absolute;top:-260px;right:-300px;width:900px;height:900px;border-radius:999px;background:{tint};overflow:hidden">'
                f'<img src="data:image/jpeg;base64,{b}" style="width:100%;height:100%;object-fit:cover;object-position:0% 100%;display:block;filter:grayscale(1) contrast(1.05);mix-blend-mode:multiply;opacity:0.9"></div>')
        l = 0.8
    else:
        disc = (f'<div style="position:absolute;top:-260px;right:-300px;width:900px;height:900px;border-radius:999px;background:{tint}"></div>'
                f'<div style="position:absolute;top:120px;right:80px;width:520px;height:520px;border-radius:999px;border:3px solid {INK};opacity:0.5"></div>')
        l = 0.55
    small = 'font-size:22px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:#A8A295'
    left = f'<div style="{small};margin-top:4px">{dateline(p)}</div>'
    chips = ''.join(f'<span style="display:inline-flex;align-items:center;padding:12px 22px;border-radius:999px;border:2px solid {col(k,0.72)};color:{col(k,0.72)};font-size:28px;font-weight:500">{LABEL[b_]}</span>' for b_, k in HUES.items())
    qsize = p.get("question_size", 124 if len(cq["q"]) <= 22 else 100)
    return page(INK, PAPER, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{INK};color:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {disc}{header(PAPER if photo else INK, l=l, left=left)}
  <div style="position:relative;margin-top:440px;{small}">{p["category"]}</div>
  <div class="display" style="position:relative;margin-top:14px;font-size:{p.get("headline_size", 58)}px;line-height:1.08;letter-spacing:-0.015em;max-width:900px;text-wrap:balance">{p["headline"]}</div>
  <div style="position:relative;margin-top:40px;display:flex;align-items:center;gap:16px">
    <div style="width:3px;height:64px;background:{hc};border-radius:2px"></div>
    <div style="display:flex;flex-direction:column;gap:6px">
      <span style="font-size:22px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:{hc}">Ages {LABEL[cq["band"]]}</span>
      <span style="font-size:30px;color:#C9C3B5">So your kid asks</span>
    </div>
  </div>
  <h1 id="text" class="display" style="position:relative;margin:18px 0 0;font-weight:400;font-size:{qsize}px;line-height:0.98;letter-spacing:-0.025em;max-width:940px;text-wrap:balance"><span style="color:{hc}">&ldquo;</span>{cq["q"]}<span style="color:{hc}">&rdquo;</span></h1>
  <div style="flex-grow:1"></div>
  <div id="floor" style="position:relative;display:flex;justify-content:space-between;align-items:center">
    <div style="display:flex;gap:12px">{chips}</div>
    <div style="font-size:30px;font-weight:500">How to answer, by age &rarr;</div>
  </div>
</div>''')


def age(p, band):
    """Numeral top-left, chip, script, why line, then the tinted "They might ask" band with that age's questions."""
    a = p["ages"][band]; h = HUES[band]; c = col(h); lab = LABEL[band]; qs = p["questions"][band]
    ch = chip("shield") if a.get("shield") else chip("talk", h, a.get("chip", "Bring it up if it fits the day"))
    qa = ''.join(f'<div style="display:flex;flex-direction:column;gap:6px"><div class="serif" style="font-size:38px;line-height:1.15;color:{c}">{q["q"]}</div>'
                 f'<div style="font-size:26px;line-height:1.35;color:{SOFT}">Try: &ldquo;{q["a"]}&rdquo;</div></div>' for q in qs)
    return page(PAPER, INK, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:64px 72px 0;background:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div class="serif" style="font-size:96px;line-height:0.8;letter-spacing:-0.04em;color:{c};margin-top:8px">{lab}</div>{wordmark(INK)}
  </div>
  <div style="margin-top:44px;display:flex;flex-direction:column">{ch}</div>
  <div style="margin-top:30px;display:flex;gap:20px;align-items:flex-start">
    <div class="serif" style="font-size:140px;line-height:0.6;color:{c};margin-top:30px">&ldquo;</div>
    <p class="serif" style="margin:0;font-size:46px;line-height:1.28;letter-spacing:-0.01em;text-wrap:pretty">{a["script"]}</p>
  </div>
  <div id="text" style="margin-top:30px;padding-left:78px;max-width:900px;font-size:26px;line-height:1.4;color:{SOFT};text-wrap:pretty"><span style="font-weight:600;letter-spacing:0.06em;text-transform:uppercase;font-size:19px;color:{c}">Why it works</span><br>{a["why"]}</div>
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
  {header(PAPER, l=0.8)}
  <div style="flex-grow:0.6"></div>
  <div style="font-size:26px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;color:#A8A295">The dinner table question</div>
  <h2 class="display" style="margin:28px 0 0;font-weight:400;font-size:92px;line-height:1.04;letter-spacing:-0.02em;max-width:920px;text-wrap:balance">{p["table_question"]}</h2>
  <p id="text" style="margin:44px 0 0;font-size:34px;line-height:1.4;color:#C9C3B5;max-width:840px">Ask it at any age. Tell us what your kid said in the comments.</p>
  <div style="flex-grow:1"></div>
  <div id="floor" style="display:flex;justify-content:space-between;align-items:flex-end;font-size:30px;color:#C9C3B5">
    <div><span style="color:{PAPER};font-weight:500">Save</span> this one for dinner.<br><span style="color:{PAPER};font-weight:500">Send</span> it to another parent.<br><span style="color:{PAPER};font-weight:500">Follow</span> for today's news, explained for your kid's age.</div>{dots(16, 12, 0.65)}
  </div>
</div>''')


def check(pg, name):
    """Return a TOO LOW message if #text sits too close to #floor or #floor runs off the slide, else None."""
    gap, bottom = pg.evaluate("(() => { const t = document.getElementById('text').getBoundingClientRect(), f = document.getElementById('floor').getBoundingClientRect();"
                              " return [f.top - t.bottom, f.bottom]; })()")
    what = {"1-cover": "the question", "5-table": "the question or the comment line"}.get(name, "the script, the why line, or a Try answer")
    if bottom > 1350 + 0.5:
        return f"TOO LOW: {name}: the bottom block runs {bottom - 1350:.0f}px past the end of the slide. Shorten {what} and re-render."
    if gap < GAP[name] - 0.5:
        return f"TOO LOW: {name}: only {gap:.0f}px of space above the bottom block (minimum {GAP[name]}). Shorten {what} and re-render."
    return None


def render(post, outdir):
    for k in ("cover_question", "table_question"):
        if k not in post: raise SystemExit(f"post.json is missing '{k}' (see posts/samples-v2-2026-09-13-evening/post.json)")
    slides = [("1-cover", cover(post)), ("2-ages-5-7", age(post, "5-7")), ("3-ages-8-12", age(post, "8-12")),
              ("4-ages-13-17", age(post, "13-17")), ("5-table", table(post))]
    os.makedirs(outdir, exist_ok=True); problems = []
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
    files, problems = render(post, sys.argv[2])
    for f in files: print(f)
    for m in problems: print(m, file=sys.stderr)
    sys.exit(1 if problems else 0)
