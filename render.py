#!/usr/bin/env python3
"""Render a Dinner Table News post (post.json) to six 1080x1350 PNGs.

usage: python render.py posts/2026-09-13-morning/post.json posts/2026-09-13-morning/
Fonts are self-hosted in fonts/. Requires playwright (chromium).
"""
import base64, json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PAPER, INK, MUTED, SOFT = "#F5F2EB", "#1B1A17", "#6B675F", "#3D3A34"
HUES = {"5-7": 155, "8-12": 250, "13-17": 305}
LABEL = {"5-7": "5–7", "8-12": "8–12", "13-17": "13–17"}
CATS = {"Technology": "oklch(0.78 0.11 85)", "Health": "oklch(0.78 0.11 20)", "Economy": "oklch(0.78 0.10 190)",
        "Government": "oklch(0.78 0.10 240)", "Climate": "oklch(0.78 0.11 140)", "Science": "oklch(0.78 0.11 300)",
        "Culture": "oklch(0.78 0.12 350)", "Security": "oklch(0.70 0.04 60)", "Good news": "oklch(0.82 0.13 95)",
        "World": "oklch(0.78 0.10 215)", "Sports": "oklch(0.78 0.12 55)"}
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


def header(fg, l=0.55):
    return f'<div style="position:relative;display:flex;justify-content:flex-end">{wordmark(fg, l=l)}</div>'


def cover(p):
    photo = p.get("photo")  # path to an image file, optional
    tint = CATS.get(p["category"], CATS["World"])
    if photo:
        b = base64.b64encode(prepare_photo(photo, p.get("photo_scale", 0.66))).decode()
        disc = (f'<div style="position:absolute;top:-260px;right:-300px;width:900px;height:900px;border-radius:999px;background:{tint};overflow:hidden">'
                f'<img src="data:image/jpeg;base64,{b}" style="width:100%;height:100%;object-fit:cover;object-position:0% 100%;display:block;filter:grayscale(1) contrast(1.05);mix-blend-mode:multiply;opacity:0.9"></div>')
        hdr = header(PAPER, l=0.8)
    else:
        disc = (f'<div style="position:absolute;top:-260px;right:-300px;width:900px;height:900px;border-radius:999px;background:{tint}"></div>'
                f'<div style="position:absolute;top:120px;right:80px;width:520px;height:520px;border-radius:999px;border:3px solid {INK};opacity:0.5"></div>')
        hdr = header(INK)
    ages = ''.join(f'<span style="color:{col(h, 0.72)}">{LABEL[k]}</span>' + ('' if k == "13-17" else f'<span style="color:#A8A295">·</span>') for k, h in HUES.items())
    return page(INK, PAPER, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{INK};color:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {disc}{hdr}
  <div style="position:relative;margin-top:500px;font-size:22px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:#A8A295">{p["category"]}</div>
  <h1 class="display" style="position:relative;margin:20px 0 0;font-weight:400;font-size:{p.get("headline_size", 92)}px;line-height:1.02;letter-spacing:-0.02em;text-wrap:pretty;max-width:900px">{p["headline"]}</h1>
  <p style="position:relative;margin:36px 0 0;font-size:32px;line-height:1.4;color:#C9C3B5;text-wrap:pretty;max-width:840px">{p["summary"]} <span style="color:#A8A295">({p["outlet"]})</span></p>
  <div style="flex-grow:1"></div>
  <div style="position:relative;display:flex;justify-content:flex-end;align-items:center;gap:14px;font-size:24px;font-weight:500"><span style="color:#C9C3B5;margin-right:4px">Explain it to kids ages</span>{ages}<span style="margin-left:6px">→</span></div>
</div>''')


def chip(kind, h=None, label=""):
    if kind == "shield":
        return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:#E6E1D6;color:{SOFT};font-size:24px;font-weight:500">'
                f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{SOFT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6l7-3z"/></svg>Don\'t raise it. If they hear it, say this:</div>')
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;gap:12px;padding:14px 22px;border-radius:999px;background:{col(h,0.93,0.045)};color:{col(h)};font-size:24px;font-weight:500">'
            f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{col(h)}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4V5z"/></svg>{label}</div>')


def age(p, band, nxt):
    a = p["ages"][band]; h = HUES[band]; c = col(h); lab = LABEL[band]
    ch = chip("shield") if a.get("shield") else chip("talk", h, a.get("chip", "Bring it up if it fits the day"))
    return page(PAPER, INK, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px 72px 0;background:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {header(INK)}
  <div style="margin-top:90px;display:flex;flex-direction:column">{ch}</div>
  <div style="margin-top:36px;display:flex;gap:20px;align-items:flex-start">
    <div class="serif" style="font-size:140px;line-height:0.6;color:{c};margin-top:30px">&ldquo;</div>
    <p class="serif" style="margin:0;font-size:{a.get("size", 46)}px;line-height:1.3;letter-spacing:-0.01em;text-wrap:pretty">{a["script"]}</p>
  </div>
  <div style="margin-top:44px;padding-left:78px;display:flex;flex-direction:column;gap:8px;max-width:900px">
    <div style="font-size:20px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{c}">Why this works at {lab}</div>
    <div style="font-size:27px;line-height:1.4;color:{SOFT};text-wrap:pretty">{a["why"]}</div>
  </div>
  <div style="flex-grow:1"></div>
  <div style="margin:0 -72px;height:300px;background:linear-gradient(180deg,{PAPER} 0%,{col(h,0.93,0.045)} 45%,{col(h,0.86,0.08)} 100%);display:flex;justify-content:space-between;align-items:flex-end;padding:0 72px 56px;box-sizing:border-box">
    <div class="serif" style="font-size:150px;line-height:0.8;letter-spacing:-0.04em;color:{c}">{lab}</div>
    <div style="font-size:24px;font-weight:500;color:{c};padding-bottom:10px">{nxt}</div>
  </div>
</div>''')


def questions(p):
    def group(band):
        c = col(HUES[band]); qs = p["questions"].get(band, [])
        if not qs: return ""
        items = ''.join(f'<div style="display:flex;flex-direction:column;gap:6px"><div class="serif" style="font-size:36px;line-height:1.2;color:{c}">{q["q"]}</div>'
                        f'<div style="font-size:25px;line-height:1.35;color:{MUTED}">Try: "{q["a"]}"</div></div>' for q in qs)
        return (f'<div style="display:flex;flex-direction:column;gap:18px"><div style="display:flex;align-items:center;gap:12px;font-size:22px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:{c}">'
                f'<span style="display:inline-block;width:16px;height:16px;border-radius:999px;background:{c}"></span>Ages {LABEL[band]}</div>{items}</div>')
    return page(PAPER, INK, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{PAPER};display:flex;flex-direction:column;position:relative;overflow:hidden">
  {header(INK)}
  <h2 class="display" style="margin:70px 0 0;font-weight:400;font-size:68px;line-height:1.05;letter-spacing:-0.02em">Questions they might ask</h2>
  <div style="margin-top:56px;display:flex;flex-direction:column;gap:44px">{group("5-7")}{group("8-12")}{group("13-17")}</div>
</div>''')


def brand():
    return page(INK, PAPER, f'''<div style="width:1080px;height:1350px;box-sizing:border-box;padding:72px;background:{INK};color:{PAPER};display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;overflow:hidden">
  <div style="flex-grow:1"></div>{wordmark(PAPER, size=96, dot=22, l=0.65, align="center")}
  <p class="serif" style="margin:64px 0 0;max-width:760px;text-align:center;font-size:40px;line-height:1.35;color:#C9C3B5;text-wrap:pretty">Today's top stories, explained for every age at your table.</p>
  <div style="flex-grow:1"></div>
  <div style="width:120px;height:2px;background:{SOFT}"></div>
  <p style="margin:40px 0 0;text-align:center;font-size:28px;line-height:1.35;color:{PAPER}">Share this with a friend, a parent, or a teacher.</p>
  <div style="margin-top:20px;font-size:24px;color:#A8A295">@dinnertablenews</div>
  <div style="height:40px"></div>
</div>''')


def render(post, outdir):
    slides = [("1-cover", cover(post)), ("2-ages-5-7", age(post, "5-7", "Ages 8–12 →")),
              ("3-ages-8-12", age(post, "8-12", "Ages 13–17 →")), ("4-ages-13-17", age(post, "13-17", "Questions they might ask →")),
              ("5-questions", questions(post)), ("6-brand", brand())]
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        for name, html in slides:
            pg.set_content(html); pg.wait_for_timeout(150)
            pg.screenshot(path=os.path.join(outdir, f"{name}.jpg"), type="jpeg", quality=92)
        b.close()
    return [os.path.join(outdir, f"{n}.jpg") for n, _ in slides]


if __name__ == "__main__":
    post = json.load(open(sys.argv[1]))
    for f in render(post, sys.argv[2]): print(f)
