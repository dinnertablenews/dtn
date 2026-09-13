#!/usr/bin/env python3
"""Pull every allowlisted feed, keep the last 48 hours, write data/headlines.json.

Runs hourly in GitHub Actions. Output is read by the scheduled Claude task that
selects stories and builds the carousel. Never adds a source that isn't in feeds.yaml.
"""
import hashlib, json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import feedparser, requests, yaml

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
WINDOW_H = 48
OUT = "data/headlines.json"


def get(url):
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=25)
    r.raise_for_status()
    return r.text


def clean(s):
    s = unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def canonical(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")


class LinkGrab(HTMLParser):
    """Collect article links from a hub page: <a href> whose text looks like a headline."""
    def __init__(self, base, domain):
        super().__init__(); self.base, self.domain = base, domain
        self.items, self._href, self._buf = [], None, []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href, self._buf = urljoin(self.base, href), []
    def handle_data(self, data):
        if self._href is not None: self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = clean(" ".join(self._buf)); u = self._href
            if (urlparse(u).netloc.endswith(self.domain) and "/article/" in u
                    and 30 <= len(text) <= 200):
                self.items.append({"title": text, "link": u})
            self._href = None


def from_rss(src, feed, now):
    d = feedparser.parse(get(feed["url"]))
    out = []
    for e in d.entries:
        ts = e.get("published_parsed") or e.get("updated_parsed")
        pub = datetime(*ts[:6], tzinfo=timezone.utc) if ts else now
        if now - pub > timedelta(hours=WINDOW_H): continue
        title = re.sub(r"\s+-\s+[^-]{2,40}$", "", clean(e.get("title")))  # Google News appends " - Outlet"
        if "|" in title or len(title) < 30: continue  # section/hub pages, not stories
        out.append({"title": title, "link": e.get("link", ""),
                    "summary": clean(e.get("summary", ""))[:600],
                    "published": pub.isoformat()})
    return out


def from_html(src, feed, now):
    p = LinkGrab(feed["url"], src["domain"]); p.feed(get(feed["url"]))
    seen, out = set(), []
    for it in p.items:
        k = canonical(it["link"])
        if k in seen: continue
        seen.add(k)
        out.append({**it, "summary": "", "published": now.isoformat(), "undated": True})
    return out[:40]


def main():
    os.makedirs("data", exist_ok=True)
    cfg = yaml.safe_load(open("feeds.yaml"))
    now = datetime.now(timezone.utc)
    items, errors = [], []
    for group, counted in (("sources", True), ("background", False)):
        for src in cfg.get(group, []):
            for feed in src["feeds"]:
                try:
                    got = from_rss(src, feed, now) if feed["kind"] == "rss" else from_html(src, feed, now)
                except Exception as ex:
                    errors.append({"source": src["id"], "url": feed["url"], "error": str(ex)[:200]}); continue
                for it in got:
                    it.update({"source": src["id"], "outlet": src["name"], "counted": counted,
                               "section": feed.get("section", "top")})
                    it["id"] = hashlib.sha1(canonical(it["link"]).encode()).hexdigest()[:12]
                    items.append(it)
                time.sleep(0.5)
    # dedupe by canonical link, keep the earliest-seen copy
    seen, uniq = set(), []
    for it in items:
        if it["id"] in seen: continue
        seen.add(it["id"]); uniq.append(it)
    uniq.sort(key=lambda x: x["published"], reverse=True)
    json.dump({"fetched_at": now.isoformat(), "window_hours": WINDOW_H,
               "count": len(uniq), "errors": errors, "items": uniq},
              open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"{len(uniq)} items, {len(errors)} feed errors", file=sys.stderr)
    for e in errors: print("  ", e["source"], e["error"], file=sys.stderr)


if __name__ == "__main__":
    main()
