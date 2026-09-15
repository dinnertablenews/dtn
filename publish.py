#!/usr/bin/env python3
"""Instagram publishing for Dinner Table News (Instagram API with Instagram Login).

usage:
  python publish.py verify                      # who is the token, can it publish
  python publish.py publish posts/<slug>        # publish the five JPGs + caption in that folder
  python publish.py refresh                     # refresh the long-lived token (prints the new one)

Env: IG_ACCESS_TOKEN (required), IG_REPO (owner/repo, default dinnertablenews/dtn), IG_REF (default main).
Images are served to Instagram from raw.githubusercontent.com, so the post folder must be committed
and pushed before publishing. Runs inside GitHub Actions; the cloud workspace can't reach graph.instagram.com.

Veto: if <folder>/HOLD exists, publish() stops without posting. The workflow sleeps until its publish_at
input and pulls main before calling this, so a HOLD pushed during the window is honoured. After a post
goes live the permalink is written to <folder>/published.json and into the slot's entry in data/log.json
(the entry whose slug is the folder name, or the folder name minus "-alt" for an alternate), so the log
is right even when no Claude session is awake to record it.
"""
import json, os, sys, time, requests

API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
REPO = os.environ.get("IG_REPO", "dinnertablenews/dtn")
REF = os.environ.get("IG_REF", "main")


def slides(folder):
    """The numbered JPGs in the post folder, in order: 1-cover ... 5-table today, six slides for older posts."""
    return sorted(f[:-4] for f in os.listdir(folder) if f[:1].isdigit() and f[1:2] == "-" and f.endswith(".jpg"))


def call(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{API}/{path}", params=params if method == "GET" else None,
                         data=None if method == "GET" else params, timeout=60)
    try: j = r.json()
    except Exception: j = {"raw": r.text[:300]}
    if r.status_code >= 400 or "error" in j:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {json.dumps(j)[:600]}")
    return j


def me():
    return call("GET", "me", fields="id,user_id,username,account_type")


def verify():
    m = me()
    lim = call("GET", f"{m['user_id']}/content_publishing_limit", fields="quota_usage,config")
    print(f"token ok: @{m['username']} ({m['account_type']}), ig user id {m['user_id']}; "
          f"publishing quota used {lim['data'][0]['quota_usage']} of {lim['data'][0]['config']['quota_total']} per day")


def record(folder, media, log_path="data/log.json"):
    """Write the permalink into the slot's log entry. The folder name is the slug, or the slug plus
    "-alt" for the alternate post; the alternate publishing means Dan chose it over the primary."""
    if not os.path.exists(log_path): return False
    slug = os.path.basename(folder.rstrip("/"))
    base = slug[:-4] if slug.endswith("-alt") else slug
    log = json.load(open(log_path))
    hits = [e for e in log if e.get("slug") == base]
    if not hits: return False
    e = hits[-1]
    e["published"] = media.get("permalink"); e["published_at"] = media.get("timestamp")
    e["chosen"] = "alternate" if slug != base else "primary"
    json.dump(log, open(log_path, "w"), indent=1, ensure_ascii=False); open(log_path, "a").write("\n")
    return True


def publish(folder):
    slug = os.path.basename(folder.rstrip("/"))
    hold = os.path.join(folder, "HOLD")
    if os.path.exists(hold):
        print(f"held: {hold} exists, not publishing. {open(hold).read().strip()[:200]}"); return
    post = json.load(open(os.path.join(folder, "post.json")))
    if os.path.exists(os.path.join(folder, "published.json")):
        raise SystemExit(f"{slug} already published: {open(os.path.join(folder, 'published.json')).read()}")
    uid = me()["user_id"]
    base = f"https://raw.githubusercontent.com/{REPO}/{REF}/{folder.rstrip('/')}"
    children = []
    for s in slides(folder):
        url = f"{base}/{s}.jpg"
        if requests.head(url, timeout=30).status_code != 200:
            raise SystemExit(f"image not reachable: {url} (is the folder pushed?)")
        c = call("POST", f"{uid}/media", image_url=url, is_carousel_item="true")
        children.append(c["id"]); time.sleep(1)
    car = call("POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(children), caption=post["caption"])
    for _ in range(30):
        st = call("GET", car["id"], fields="status_code,status")
        if st["status_code"] == "FINISHED": break
        if st["status_code"] == "ERROR": raise SystemExit(f"container error: {st}")
        time.sleep(5)
    pub = call("POST", f"{uid}/media_publish", creation_id=car["id"])
    media = call("GET", pub["id"], fields="id,permalink,timestamp")
    json.dump(media, open(os.path.join(folder, "published.json"), "w"), indent=1)
    logged = record(folder, media)
    print(f"published {slug}: {media.get('permalink')}" + ("" if logged else " (no log entry to update)"))


def refresh():
    j = call("GET", "refresh_access_token", grant_type="ig_refresh_token")
    print(json.dumps({"expires_in_days": round(j["expires_in"] / 86400, 1)}))
    open(os.environ.get("IG_NEW_TOKEN_FILE", "/tmp/ig_new_token"), "w").write(j["access_token"])


if __name__ == "__main__":
    if not TOKEN: raise SystemExit("IG_ACCESS_TOKEN not set")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"verify": verify, "publish": lambda: publish(sys.argv[2]), "refresh": refresh}[cmd]()
