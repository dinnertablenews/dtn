#!/usr/bin/env python3
"""Instagram publishing for Dinner Table News (Instagram API with Instagram Login).

usage:
  python publish.py verify                      # who is the token, can it publish
  python publish.py publish posts/<slug>        # publish the five JPGs + caption in that folder
  python publish.py refresh                     # refresh the long-lived token (prints the new one)

Env: IG_ACCESS_TOKEN (required), IG_REPO (owner/repo, default dinnertablenews/dtn), IG_REF (default main).
Images are served to Instagram from raw.githubusercontent.com, so the post folder must be committed
and pushed before publishing. Runs inside GitHub Actions; the cloud workspace can't reach graph.instagram.com.
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


def publish(folder):
    slug = os.path.basename(folder.rstrip("/"))
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
    print(f"published {slug}: {media.get('permalink')}")


def refresh():
    j = call("GET", "refresh_access_token", grant_type="ig_refresh_token")
    print(json.dumps({"expires_in_days": round(j["expires_in"] / 86400, 1)}))
    open(os.environ.get("IG_NEW_TOKEN_FILE", "/tmp/ig_new_token"), "w").write(j["access_token"])


if __name__ == "__main__":
    if not TOKEN: raise SystemExit("IG_ACCESS_TOKEN not set")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"verify": verify, "publish": lambda: publish(sys.argv[2]), "refresh": refresh}[cmd]()
