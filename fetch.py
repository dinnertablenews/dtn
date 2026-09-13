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
import trafilatura
try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # optional
    gnewsdecoder = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
WINDOW_H = 48
OUT = "data/headlines.json"
ARTICLES = "data/articles.json"   # id -> {url, text, fetched_at}; text is what the writer reads
TEXT_MAX = 6000
TEXT_BUDGET = 120                  # new articles fetched per run


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
        body = clean(e.content[0].value) if e.get("content") else ""   # WordPress feeds ship the full article
        if len(body) < 400: body = clean(e.get("summary", ""))          # some feeds put the first paragraphs here
        out.append({"title": title, "link": e.get("link", ""),
                    "summary": clean(e.get("summary", ""))[:600],
                    "published": pub.isoformat(), "_body": body[:TEXT_MAX]})
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


def resolve(url):
    """Google News RSS links are encoded redirects; decode to the publisher URL."""
    if "news.google.com" in url and gnewsdecoder:
        try:
            r = gnewsdecoder(url, interval=1)
            if r.get("status"): return r["decoded_url"]
        except Exception: pass
    return url


def fetch_articles(items, now):
    """Store article text for recent counted items so the writer can work from the reporting, not the RSS blurb."""
    try: cache = json.load(open(ARTICLES))
    except Exception: cache = {}
    fresh = [i for i in items if i.get("counted") and now - datetime.fromisoformat(i["published"]) <= timedelta(hours=30)]
    budget = TEXT_BUDGET
    status = {}
    for i in fresh:
        prev = cache.get(i["id"])
        if prev and (prev["ok"] or now - datetime.fromisoformat(prev["fetched_at"]) < timedelta(hours=3)): continue
        if budget <= 0: break
        budget -= 1
        url = prev["url"] if prev else resolve(i["link"])
        text, code = "", 0
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,*/*", "Accept-Language": "en-US,en"},
                             timeout=25, allow_redirects=True)
            code = r.status_code
            if r.ok:
                text = (trafilatura.extract(r.text, url=url, include_comments=False, include_tables=False,
                                            favor_precision=True)
                        or trafilatura.extract(r.text, url=url, include_comments=False, include_tables=False)
                        or trafilatura.baseline(r.text)[1] or "")
        except Exception as ex:
            code = str(ex)[:60]
        if len(text) < 400 and code in (401, 403, 429, 503):
            # outlet blocks datacenter IPs; fetch the same page through a reader proxy
            try:
                r = requests.get(f"https://r.jina.ai/{url}", timeout=40,
                                 headers={"User-Agent": UA, "Accept": "text/plain", "X-Return-Format": "text"})
                if r.ok and len(r.text) > 400:
                    text, code = re.sub(r"\n{3,}", "\n\n", r.text).strip(), f"{code}/reader"
                else:
                    code = f"{code}/reader{r.status_code}:{clean(r.text)[:60]}"
            except Exception as ex:
                code = f"{code}/reader-err:{str(ex)[:60]}"
        if len(text) < 400 and len(i.get("_body", "")) > 400:
            text, code = i["_body"], f"{code}/rss"
        status.setdefault(urlparse(url).netloc, []).append(code)
        cache[i["id"]] = {"url": url, "text": text[:TEXT_MAX], "fetched_at": now.isoformat(), "ok": bool(text), "http": code}
        time.sleep(0.3)
    for host, codes in sorted(status.items()):
        print(f"  {host}: {codes[:3]}", file=sys.stderr)
    # keep cache bounded: drop entries older than 4 days
    cutoff = (now - timedelta(days=4)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("fetched_at", "") >= cutoff}
    json.dump(cache, open(ARTICLES, "w"), ensure_ascii=False)
    for i in items:
        i.pop("_body", None)
        c = cache.get(i["id"])
        if c: i["article_url"] = c["url"]; i["has_text"] = c["ok"]
    print(f"articles cached: {len(cache)}, with text: {sum(1 for v in cache.values() if v['ok'])}", file=sys.stderr)


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
    fetch_articles(uniq, now)
    json.dump({"fetched_at": now.isoformat(), "window_hours": WINDOW_H,
               "count": len(uniq), "errors": errors, "items": uniq},
              open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"{len(uniq)} items, {len(errors)} feed errors", file=sys.stderr)
    for e in errors: print("  ", e["source"], e["error"], file=sys.stderr)


if __name__ == "__main__":
    main()
