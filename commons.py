#!/usr/bin/env python3
"""Fetch the Wikipedia infobox image for a subject from Wikimedia Commons, with license metadata.

usage: python commons.py "Dario Amodei" [slug]
Writes data/images/<slug>.jpg and data/images/<slug>.json. Exits 2 if no usable image
(missing, too small, or license not CC/PD). Runs inside GitHub Actions (Commons blocks
the cloud workspace).
"""
import json, os, re, sys, requests

UA = "DinnerTableNews/1.0 (https://dinnertablenews.com; bot@dinnertablenews.com)"
OK = re.compile(r"^(cc0|cc[- ]by(?:[- ]sa)?(?:[- ]\d\.\d)?|public domain|pd[- ].*|attribution)", re.I)
MIN_PX = 800


def api(host, params):
    r = requests.get(f"https://{host}/w/api.php", params={**params, "format": "json"}, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status(); return r.json()


def main(subject, slug=None):
    slug = slug or re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    os.makedirs("data/images", exist_ok=True)
    log = open(f"data/images/{slug}.log", "w")
    def fail(msg): log.write(msg + "\n"); log.close(); print(msg, file=sys.stderr); sys.exit(2)
    q = api("en.wikipedia.org", {"action": "query", "prop": "pageimages", "piprop": "name|original", "titles": subject, "redirects": 1})
    page = next(iter(q["query"]["pages"].values()))
    log.write(json.dumps(page)[:1500] + "\n")
    name = page.get("pageimage"); orig = page.get("original")
    if not name or not orig: fail("no infobox image")
    w, h = orig.get("width", 0), orig.get("height", 0)
    if min(w, h) < MIN_PX: fail(f"too small: {w}x{h}")
    info = api("commons.wikimedia.org", {"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata", "titles": f"File:{name}"})
    ii = next(iter(info["query"]["pages"].values())).get("imageinfo", [{}])[0]
    meta = ii.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    log.write(json.dumps({k: str(v.get("value", ""))[:200] for k, v in meta.items()}) + "\n")
    if not OK.match(lic): fail(f"license not usable: {lic!r}")
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
    img = requests.get(orig["source"], headers={"User-Agent": UA}, timeout=60); img.raise_for_status()
    ext = ".png" if orig["source"].lower().endswith(".png") else ".jpg"
    open(f"data/images/{slug}{ext}", "wb").write(img.content)
    json.dump({"subject": subject, "file": f"data/images/{slug}{ext}", "commons_file": name, "width": w, "height": h,
               "license": lic, "artist": artist, "page": ii.get("descriptionurl", ""),
               "credit": f"Photo: {artist or 'Wikimedia Commons'}, Wikimedia Commons, {lic}"},
              open(f"data/images/{slug}.json", "w"), indent=1, ensure_ascii=False)
    log.write("ok\n"); log.close()
    print(f"data/images/{slug}{ext} {w}x{h} {lic} {artist}")


if __name__ == "__main__":
    main(*sys.argv[1:])
