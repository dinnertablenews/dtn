#!/usr/bin/env python3
"""Draw the publish time for a slot: the slot time plus or minus config.publish_window_minutes, uniformly at random.

usage: python target.py <morning|noon|evening> [YYYY-MM-DD]
Prints one JSON line: {"target": "<ISO time in config.timezone>", "seconds": <seconds from now, 0 if the target has passed>}.
Draw once per run and record the target in the log entry. The run should start at least window + 30 minutes
before the slot so the wait fits in one wake-up (max 60 minutes).
"""
import datetime as dt, json, random, sys
from zoneinfo import ZoneInfo

cfg = json.load(open("config.json"))
slot = sys.argv[1]
tz = ZoneInfo(cfg["timezone"]); now = dt.datetime.now(tz)
day = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else now.date()
h, m = map(int, cfg["slots"][slot].split(":"))
w = cfg.get("publish_window_minutes", 0)
offset = random.SystemRandom().randint(-w, w) if w else 0
target = dt.datetime.combine(day, dt.time(h, m), tz) + dt.timedelta(minutes=offset)
print(json.dumps({"target": target.isoformat(timespec="minutes"), "seconds": max(0, int((target - now).total_seconds()))}))
