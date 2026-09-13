#!/usr/bin/env python3
"""Cluster the last 24h of headlines across outlets and rank the clusters.

usage: python rank.py data/headlines.json [hours] > candidates.json
Ranking: number of distinct counted outlets covering the cluster (the "top story"
signal), then recency. The Claude task reads the top ~15 clusters, applies the
7-day category log, picks three (one positive), and writes the post.
"""
import json, re, sys
from datetime import datetime, timedelta, timezone

STOP = set("a an the of to in on for and or at by with from as is are was were be been has have had it its this that these those "
           "after over into out up down new says said say will would could should can may might us u.s. vs amid latest news update "
           "how what why when who where here their his her they he she about more than one two three first".split())


def toks(t):
    t = re.sub(r"[’']s\b", "", t.lower())
    return {w for w in re.findall(r"[a-z0-9][a-z0-9\-]+", t) if w not in STOP and len(w) > 2}


def main(path, hours=24):
    d = json.load(open(path)); now = datetime.now(timezone.utc)
    items = [i for i in d["items"] if now - datetime.fromisoformat(i["published"]) <= timedelta(hours=hours)]
    for i in items: i["_t"] = toks(i["title"])
    clusters = []
    for i in sorted(items, key=lambda x: x["published"], reverse=True):
        for c in clusters:
            for j in c["items"]:
                inter = len(i["_t"] & j["_t"]); small = min(len(i["_t"]), len(j["_t"])) or 1
                if inter >= 3 and inter / small >= 0.4:
                    c["items"].append(i); break
            else: continue
            break
        else:
            clusters.append({"items": [i]})
    out = []
    for c in clusters:
        outlets = sorted({i["outlet"] for i in c["items"] if i.get("counted")})
        if not outlets: continue
        newest = max(i["published"] for i in c["items"])
        out.append({"outlets": outlets, "n_outlets": len(outlets), "n_items": len(c["items"]), "newest": newest,
                    "headlines": [{"outlet": i["outlet"], "title": i["title"], "link": i["link"], "summary": i.get("summary", "")[:300]}
                                  for i in c["items"][:6]]})
    out.sort(key=lambda c: (c["n_outlets"], c["n_items"], c["newest"]), reverse=True)
    json.dump({"generated": now.isoformat(), "window_hours": hours, "clusters": out[:40]}, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 24)
