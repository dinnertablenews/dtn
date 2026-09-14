# Dinner Table News — scheduled run

You are the automated run for one posting slot. Do everything below without asking questions; there is no one to answer. If a step fails after two tries, write what happened to `runs/<slug>.log`, push it, and stop.

## 0. Setup
- Clone `https://github.com/dinnertablenews/dtn` and work in the clone. This scheduled task was created with the repo selected, so `git push` works; if it returns 403 "not in this session's authorized repository set", the task lost its repository binding: write that to `runs/<slug>.log` locally, make it the first line of your final message, and stop.
- Read `config.json`. If `dry_run` is true, do every step except §7.
- Determine the slot from the current time in America/Chicago: run at ~06:10 → `morning` (posts 07:00); ~11:10 → `noon` (12:00); ~19:10 → `evening` (20:00). Slug = `YYYY-MM-DD-<slot>`. If `posts/<slug>/` already exists, stop.
- Each post goes live at a random minute inside a window around its slot time, ± `publish_window_minutes` from `config.json` (10 today: noon lands between 11:50 and 12:10). The scheduled task fires 40 minutes before the window opens, so the wait from the end of the build to the latest possible target fits in one wake-up. Draw the target now, once: `python target.py <slot>` prints `{"target": ..., "seconds": ...}`. Keep the target for §6 and §7. Never draw it a second time.
- `pip install --break-system-packages feedparser requests pyyaml playwright pillow` if needed. Playwright's Chromium is preinstalled in this environment.
- Workflow dispatches: use the GitHub MCP tool available in this session (run a workflow / `actions.createWorkflowDispatch` on `dinnertablenews/dtn`, ref `main`, with the inputs). `gh api` and `gh workflow run` return 403 in scheduled runs; don't try them.

## 1. Candidates
- `python rank.py data/headlines.json 30 > /tmp/cand.json`. Output is `{generated, window_hours, clusters: [...]}`; read the top 15 clusters.
- Read `data/log.json` (rolling record of what ran: slug, category, cluster headline, photo yes/no). Create it if missing.

## 2. Pick the story for this slot
Rules, in order:
1. Never repeat a story already in `data/log.json` from the last 7 days (same event, even if the headline moved on).
2. Same lead subject at most one slot per day. The lead subject is the person, institution, or country the headline is about (the one who would take the photo). If a slot's pick would repeat the lead subject of a post already in today's log, skip to the next cluster with a different lead subject, unless the story is the clear top story of the day: it leads the ranking by at least two outlets over the next cluster. Write the skip or the override in the log note.
3. `morning` takes the #1 cluster of the day unless it ran yesterday evening; then #2.
4. `evening` is the positive story: the most uplifting cluster in the top 15 (science, rescue, record, recovery, a win). Category label "Good news". If nothing qualifies, take the least grim story and label it by its real category.
5. `noon` takes the highest-ranked remaining cluster, with a tie-break for category diversity: if two clusters are within one outlet of each other, prefer the category that appears least in the last 7 days of the log.
6. Any story is fair game, including violence, abuse, suicide. That is the point of the account. Handle it with the Shield rule in §4.
7. Category is one of: Technology, Health, Economy, Government, Climate, Science, Culture, Security, World, Sports, Good news.

## 3. Facts
- The outlets are not reachable from this environment. Read the article text from `data/articles.json` (keyed by each headline's `id`; `text` is the extracted article, `url` the resolved publisher link). Use the two or three articles in the cluster that have text. If none has text, use the RSS summaries and say so in the log. Write from what the articles say. No detail that isn't in them. Attribute the summary to the outlet whose article you leaned on most; that outlet's name goes in `outlet` and its URL in `source_url`.
- If the story has one clear subject who is a public figure, or a landmark/spacecraft/institution, set `photo_subject` to the exact Wikipedia article title. Otherwise leave it out. Never a private individual, victim, suspect, or minor. Never on a death, arrest, or scandal about the subject. Never the same subject as any of the last three log entries. Skip the photo if the last two entries in the log both had photos. The positive story may take a photo more freely.

## 4. Write `post.json`
Same schema as `posts/samples-v2-2026-09-13-evening/post.json`. The carousel is five slides: cover, one card per age with its questions on it, and a closing dinner-table question. Voice and rules:
- Dan's voice: open with a concrete fact, not a warm-up. Short declarative sentences, active voice, subject-verb-object. Dry aside allowed, never a joke that takes over. No adjectives that don't do work. Trust the reader with specifics.
- None of the AI tells: no "not just X but Y", no rule-of-three lists for effect, no "it's important to note", no "serves as", "testament", "underscores", "landscape", "delve", "vibrant", no em-dash chains, no tidy moral at the end, no hedged summary sentence.
- `date`: the posting date in America/Chicago, `YYYY-MM-DD`. The cover shows it written out ("September 13, 2026"). Never a slot or a time of day anywhere on the slides.
- Cover: `headline` ≤ 60 characters, two lines at most. `summary` 3–5 sentences, ≤ 340 characters. The summary is not on the cover; it goes in the caption.
- `cover_question`: `{"band": "<5-7|8-12|13-17>", "q": "..."}`. The cover leads with a question a kid would ask about this story, tagged with the age it comes from. Rotation: find the last entry in `data/log.json` that has a `cover_band` and take the next bracket in the order 5–7 → 8–12 → 13–17 → 5–7; if none, 5–7. The question must be one of that bracket's entries in `questions`, so its answer is on that age's card, and it must read as a question about the headline. ≤ 40 characters; ≤ 22 keeps the biggest type.
- `cover_answer`: the parent's one-line answer to the cover question, ≤ 60 characters, no hedge ("Not yet, and maybe not." / "No. Just quiet this year."). It is the first line of the caption, so under the cover in the feed the cover asks and the caption answers. It must be true to the articles.
- `source_domain`: the outlet's domain as it should read in the caption, e.g. `pbs.org/newshour`, `apnews.com`, `bbc.com`.
- `hashtags`: exactly four CamelCase tags, in this order: `#Parenting`, `#KidsAndNews`, **one** tag naming what this story is about, `#DinnerTableNews`. e.g. `["#Parenting", "#KidsAndNews", "#Congress", "#DinnerTableNews"]`. The third slot is the only free one. Make it specific — a name, place, bill, company, event. Never a category label (`#Economy`, `#Government`, `#GoodNews`, `#World`…): the cover already prints the category, so a tag that repeats it is wasted. `render.py` fails the render with a `HASHTAGS:` line if the list is the wrong length, the wrong shape, or the story tag is generic.
- Questions: 1 for 5–7, 2 for 8–12, 2 for 13–17, each with a "Try:" answer ≤ 160 characters. Real questions a kid would ask, including the awkward ones. They render on that age's card in the "They might ask" band.
- Ages 5–7: 2–4 sentences, concrete, one physical comparison, ends with reassurance or "the grown-ups have it." Open with the story, not a definition. Set `shield: true` when a parent should not raise the story unprompted (violence, death, abuse, sexual content, anything a 5-year-old can't do anything with). Then the script is what to say only if the child hears about it.
- Ages 8–12: one cause-and-effect chain they can follow, one familiar mechanism (checklist, referee, thermostat). 3–4 sentences. `chip`: "Bring it up if it fits the day" or "Good one to bring up".
- Ages 13–17: lead with a real question, then a second one. Treat them as a conversation partner. 3–4 sentences. `chip`: "Ask first, then talk".
- `why` lines: one or two sentences on why this works at that age, in plain language.
- `table_question`: one question anyone at the table can answer without knowing the news, drawn from the story's tension (a rule, a choice, a fairness call). ≤ 70 characters. It is the last slide and the comment prompt.
- `caption`: do not write it. Leave the field out; `render.py` builds it from the fields above and writes it into `post.json` on the first render. The order is fixed: `cover_answer`, the summary, "Source: <outlet>, <source_domain>" with the photo credit line under it if a photo ran, "Swipe for what to say at 5, at 10, and at 15.", "The dinner table question: <table_question> Tell us what your kid said, and how old they are.", the hashtags. If you change a field after the first render, delete `caption` and render again; a caption that doesn't match its fields fails the render with a `CAPTION:` line.

## 5. Photo (only if `photo_subject` is set)
- Dispatch `commons.yml` via the GitHub MCP tool with inputs `subject=<title>`, `slug=<slug>`, ref `main`. Wait ~90 s, `git pull`. If `data/images/<slug>.json` exists, set `photo` to its `file` and `photo_credit` to its `credit`, then delete `caption` from `post.json` so the next render rebuilds it with the credit line. If not, no photo; carry on.

## 6. Render and push
- `python render.py posts/<slug>/post.json posts/<slug>/`
- `render.py` measures every slide and exits non-zero with a `TOO LOW:` line naming the slide when text sits too close to what follows it: on each age card at least 72px of paper between the "Why it works" line and the "They might ask" band, and the band must end inside the card; on the cover the question must clear the age-chip row; on the table slide the comment line must clear the save/send/follow block. Shorten the text it names (the script, the why line, a Try answer, the question) and re-render until it exits 0. Never commit or publish a post whose render fails this check, and never work around it by changing sizes or the check itself; the three age cards must match.
- Look at the five JPGs (Read them). Fix anything that overflows or wraps badly by shortening text, then re-render. Cover headline two lines at most; cover question two lines at most. Count lines in the image before telling Dan how many there are.
- Append an entry to `data/log.json` with `cover_band` set to the cover question's bracket and `publish_target` set to the drawn target. Commit `posts/<slug>/` and `data/log.json`, push to `main`.
- Write a two-line summary for the notification: the headline and the target time ("Posts at 11:57 CT"). It reaches Dan's phone when this run finishes.

## 7. Veto window and publish (skipped when `dry_run` is true)
Dan gets a phone notification only when this run's turn ends, so the window works like this:
- The wait ends at the target drawn in §0, not after a fixed 50 minutes. Re-run `python target.py` only to read the clock: it draws a new random minute every time, so never take a fresh target from it; compute the remaining seconds yourself as target minus now.
- If a `send_later` (schedule a message to this session) tool is available: schedule a wake-up for this same session for the seconds remaining until the target (at least 60; if more than 3600 remain, schedule 3600 and re-arm for the rest when it fires), then END YOUR TURN with the two-line summary from §6 plus "Reply kill, skip, or hold here to stop this post." That ending is what pings Dan. When the wake-up fires: if Dan replied with "kill", "skip", or "hold", stop and note it in the log. If he replied with a swap instruction, follow it (re-run §3–6 for the story he named), then publish.
- `ScheduleWakeup` counts as that tool, but it holds only one pending wake-up and Dan's next message replaces it. So every time Dan replies before the target (an edit, a question, anything short of kill/skip/hold), handle it, then schedule the wake-up again for the seconds still remaining until the target before ending the turn. Never end a turn before the target without a wake-up pending. If the target has already passed when you notice, or the run started late and the build finished after the target, publish immediately and say so.
- If no such tool exists: stay in the turn and wait it out: `sleep` in chunks of at most 300 seconds until the target. Dan's replies in this conversation arrive between tool calls; check for "kill", "skip", "hold", or a swap after each sleep and act on them the same way. Then publish.
- Publish: dispatch `publish.yml` via the GitHub MCP tool with inputs `action=publish`, `folder=posts/<slug>`, ref `main`. Wait ~2 minutes, `git pull`, read `posts/<slug>/published.json` (the workflow commits it) for the permalink, record it in the log entry, push. End with the headline and the permalink.

## Guardrails
- Sources are only the outlets in `feeds.yaml`. Never introduce another.
- Never invent a quote, number, or name. If the articles don't say it, the post doesn't say it.
- If the top story is something you cannot write responsibly for kids at all (e.g., detailed sexual violence with no way to frame it), pick the next story and note why in the log. This should be rare; the Shield exists for hard stories.
