# Dinner Table News — Product Requirements Document

Version 1.0 · September 14, 2026 · Owner: Dan

This document describes the system well enough to rebuild it from scratch. Where the repository holds the authoritative rule (TASK.md, render.py), this document summarizes and points at it. The repository is `github.com/dinnertablenews/dtn`.

## 1. Product

Dinner Table News is an Instagram account (`@dinnertablenews`) that publishes three carousel posts a day. Each post takes one current news story and gives parents the words to explain it to a child at three ages: 5–7, 8–12, and 13–17. Every post ends with one question the whole family can answer at dinner.

The product promise, in the account's own words: "today's news, explained for your kid's age."

The pipeline is fully automated. A scheduled Claude task selects the story, writes the post, renders the slides, waits through a veto window in which Dan can stop it from his phone, and publishes to Instagram. Humans touch it only to veto, swap, or change the rules.

## 2. Audience and voice

**Audience.** Parents of one kid. A parent reading the post cares about one age band, theirs. Copy never counts the bands ("three ages") at the reader; it names the kid's age.

**Voice (Dan's).** Open with a concrete fact, not a warm-up. Short declarative sentences, active voice, subject-verb-object. Dry aside allowed, never a joke that takes over. No adjectives that don't do work. Trust the reader with specifics.

**Forbidden tells.** No "not just X but Y", no rule-of-three lists for effect, no "it's important to note", no "serves as", "testament", "underscores", "landscape", "delve", "vibrant", no em-dash chains, no tidy moral at the end, no hedged summary sentence.

**Facts.** Never invent a quote, number, or name. If the source articles don't say it, the post doesn't say it. Sources are only the outlets in the allowlist.

**Hard stories.** Any story is fair game, including violence, abuse, and suicide. That is the point of the account. Hard stories carry a "shield" on the 5–7 card: don't raise it; if the child hears about it, say this.

## 3. System overview

```
feeds.yaml ──► fetch.py (GitHub Action, hourly) ──► data/headlines.json, data/articles.json
                                                          │
scheduled Claude task (06:10, 11:10, 19:10 CT) ◄──────────┘
   │  rank.py → pick primary + alternate → write two post.json → commons.yml (photos) → render.py → push
   │  → dispatch publish.yml with publish_at → notify Dan
   ▼
publish.yml (GitHub Action): sleep to publish_at → pull main → stop if <folder>/HOLD → publish → log permalink
   ▼
Instagram (Graph API, images served from raw.githubusercontent.com)
```

Three runtimes:

1. **GitHub Actions** (always on): fetch headlines hourly, fetch a Wikimedia Commons image on demand, publish to Instagram on demand, refresh the Instagram token weekly.
2. **The scheduled Claude task** (three times a day): everything editorial. It runs in Claude Code's cloud sandbox, which cannot reach news sites, Wikimedia, or Instagram, so those calls are delegated to Actions.
3. **Dan's phone**: receives one notification per run naming the primary and the alternate, can reply kill / skip / hold / alt / swap during the window.

## 4. Repository layout

| Path | Role |
|---|---|
| `TASK.md` | The scheduled task's instructions. The editorial and operational rulebook. Authoritative. |
| `config.json` | `dry_run`, slot times, `publish_window_minutes`, timezone. |
| `feeds.yaml` | Source allowlist. Nothing outside it is ever fetched. |
| `fetch.py` | Hourly fetcher: feeds → `data/headlines.json`; article text → `data/articles.json`. |
| `rank.py` | Clusters the last N hours of headlines across outlets and ranks the clusters. |
| `render.py` | Renders `post.json` to five JPGs, enforces layout rules, builds the caption. |
| `commons.py` | Fetches a Wikipedia infobox image with license metadata (runs in Actions). |
| `publish.py` | Instagram publish / verify / token refresh (runs in Actions). |
| `target.py` | Draws the random publish minute inside the slot window. |
| `.github/workflows/` | `fetch.yml`, `commons.yml`, `publish.yml`, `refresh.yml`. |
| `data/log.json` | Rolling record of every run: what ran, category, photo, cover band, target, permalink. |
| `data/images/` | Commons images and their metadata, one per slug. |
| `posts/<slug>/` | `post.json`, five JPGs, `published.json` after publish. |
| `posts/samples-v2-*/` | Reference post in the current schema. |
| `runs/<slug>.log` | Written only when a run fails after two tries. |
| `fonts/` | Self-hosted woff2: Libre Caslon Display, Libre Caslon Text, Instrument Sans. |

## 5. Sources and fetching

**Allowlist** (`feeds.yaml`): AP News (via Google News RSS, because AP blocks datacenter IPs), BBC News, PBS NewsHour, The Hill, Semafor, Axios, KFF Health News, Science News, Defense One, Inside Climate News. NASA is a background source not counted in cross-outlet scoring. Each source has an id, display name, domain, and one or more feeds; a feed may carry a `section` tag (e.g. climate) for category depth.

**fetch.py** runs hourly at :17 UTC. It pulls every feed, keeps items from the last 48 hours, dedupes by canonical link keeping the earliest copy, resolves Google News links to publisher URLs, and extracts article text with trafilatura (up to 6,000 characters, budget 120 new articles per run). Output:

- `data/headlines.json`: `{fetched_at, window_hours, count, errors, items[]}`. Each item: `title, link, summary, published, source, outlet, counted, section, id, article_url, has_text`.
- `data/articles.json`: `{id: {url, text, fetched_at, ok, tries, http}}`.

The workflow commits both files to `main` with `git pull --rebase -X theirs` so it never blocks on a concurrent push.

## 6. Ranking and story selection

**rank.py** (`python rank.py data/headlines.json 30 > /tmp/cand.json`): tokenizes titles, drops stopwords, and clusters any two items sharing at least 3 tokens and at least 40% of the smaller token set. Clusters are ranked by number of distinct counted outlets, then item count, then recency. Output: top 40 clusters with outlets, counts, newest timestamp, and up to six headlines each.

**Selection rules** (TASK.md §2), in order:

1. Never repeat a story already in the log from the last 7 days, even if the headline moved on.
2. Same lead subject at most one slot per day, unless the story is the clear top story (leads by two or more outlets). The lead subject is the person, institution, or country the headline is about.
3. Morning takes the #1 cluster unless it ran the previous evening; then #2.
4. Evening is the positive story: the most uplifting cluster in the top 15 (science, rescue, record, recovery, a win), labelled "Good news". If nothing qualifies, the least grim story, labelled by its real category.
5. Noon takes the highest-ranked remaining cluster, with a category-diversity tie-break when two clusters are within one outlet of each other.
6. Categories: Technology, Health, Economy, Government, Climate, Science, Culture, Security, World, Sports, Good news.

**Facts** (TASK.md §3): write only from the two or three articles in the cluster that have text; if none has text, use RSS summaries and say so in the log. Attribute to the outlet leaned on most.

**Photo**: only if the story has one clear subject who is a public figure, or a landmark, spacecraft, or institution. Never a private individual, victim, suspect, or minor. Never on a death, arrest, or scandal about the subject. Never the same subject as any of the last three log entries. Skip if the last two entries both had photos. The positive story may take a photo more freely.

## 7. The post: `post.json` schema

| Field | Meaning |
|---|---|
| `slot` | Record only, e.g. `2026-09-14 12:00 CT`. Never rendered. |
| `date` | Posting date, `YYYY-MM-DD`. Rendered on the cover as "September 14, 2026". |
| `category` | One of the eleven categories. Drives the cover tint. |
| `outlet`, `source_url`, `source_domain` | Attribution. Domain as it should read in the caption. |
| `headline` | ≤ 60 characters, two lines on the cover. |
| `summary` | 3–5 sentences, ≤ 340 characters. Caption only. |
| `cover_question` | `{band, q}`. A question a kid of that age would ask about this story. ≤ 40 characters. Must be one of that band's `questions`. |
| `cover_answer` | The parent's one-line answer, ≤ 60 characters, no hedge. First line of the caption. |
| `table_question` | One question anyone at the table can answer without knowing the news. ≤ 70 characters. |
| `ages.<band>` | `chip`, `script`, `why`, optional `shield: true`. |
| `questions.<band>` | 1 for 5–7, 2 each for 8–12 and 13–17; each `{q, a}` with the "Try:" answer ≤ 160 characters. |
| `hashtags` | Exactly 4: `#Parenting`, `#KidsAndNews`, one story tag, `#DinnerTableNews`. The story tag is never a category label. Enforced, see the hashtag rule. |
| `photo`, `photo_credit` | Set when a Commons image landed. Optional `photo_focus_x` (default `50%`) shifts the crop left or right; the vertical anchor is fixed, see the photo rule. |
| `caption` | Built by render.py from the fields above. Not hand-written. |

**Cover question rotation.** Take the last log entry with a `cover_band` and use the next band in 5–7 → 8–12 → 13–17 → 5–7. If none, 5–7. Over a day the three posts lead with three different ages.

**Age scripts.**

- 5–7: 2–4 sentences, concrete, one physical comparison (a toll on a bridge, a permission slip), ends with reassurance or "the grown-ups have it." Opens with the story, not a definition. Shield when a parent should not raise it unprompted.
- 8–12: one cause-and-effect chain and one familiar mechanism (checklist, referee, thermostat). 3–4 sentences. Chip: "Bring it up if it fits the day" or "Good one to bring up".
- 13–17: lead with a real question, then a second one. Treat them as a conversation partner. 3–4 sentences. Chip: "Ask first, then talk".
- `why`: one or two plain sentences on why the script works at that age.

## 8. The carousel: five slides at 1080 × 1350

Rendered by `render.py` with Playwright/Chromium from inline HTML. Palette: paper `#F5F2EB`, ink `#1B1A17`, soft `#3D3A34`, muted `#6B675F`. Age hues in OKLCH: 5–7 green (155), 8–12 blue (250), 13–17 purple (305). Each category has a tint for the cover disc. Fonts: Libre Caslon Display for headlines, Libre Caslon Text for scripts and numerals, Instrument Sans for everything else. Wordmark ("Dinner / Table / News" plus three age dots) top-right on every slide.

1. **Cover** (ink background). Dateline top-left. A 900px category-tinted disc top-right, carrying the duotone photo when there is one, or a thin ring when not. Category label, headline at 58px, then a connector in the cover band's color ("AGES 8–12 / So your kid asks"), then the kid's question at 100px with colored quote marks — one size on every cover, so the grid never steps down on a long question. There is no character cap; length is bounded by the layout check instead. Two lines (about 50 characters) always fits, three lines only when the headline is one line. Footer: three outlined age chips and "How to answer, by age →".

**Photo rule** (enforced by `render.py`, not auto-fixed). The disc hangs off the top and right edges of the slide, so only a 600×640 corner of it is visible. The photo is sized to that corner, with a few pixels of bleed past the slide edge, and anchored to the **top** of its frame. Two consequences, both deliberate: the photo covers every on-slide pixel of the disc, so no strip of bare category tint can show along an edge; and any part of the image that does not fit is cropped off the **bottom**, so a crop never takes the subject's head. Only the horizontal focus is tunable (`photo_focus_x`) — the vertical anchor is not, because that is the axis that decapitates people. `check_photo()` re-measures the rendered image on every run and fails with a `PHOTO:` line on stderr if either guarantee breaks.
2. **Ages 5–7**, 3. **Ages 8–12**, 4. **Ages 13–17** (paper background). Numeral top-left in the band color, chip, the script at 46px serif with a large opening quote mark, "WHY IT WORKS" line, then a tinted "THEY MIGHT ASK" band at the bottom carrying that band's questions and Try answers. Band footer: "Save this for dinner" left, next-slide cue right ("Ages 8–12 →", "Ages 13–17 →", "One for the whole table →").
5. **The dinner table question** (ink background). Label, the question at 92px, "Ask it at any age. Tell us what your kid said in the comments.", then three asks bottom-left: **Save** this one for dinner. **Send** it to another parent. **Follow** for today's news, explained for your kid's age.

There is no brand card. The wordmark is on every slide and the follow ask lives on the last one.

**Layout rule (enforced, never auto-fixed).** Every slide has a text block and a floor. On each age card there must be at least 72px of paper between the why line and the band, and the band must end inside the card. On the cover the question must clear the chip row; on the table slide the comment line must clear the asks. A failing slide prints `TOO LOW: <slide>: ...` and the render exits 1. The fix is always shorter text. Type sizes are never reduced, so the three age cards always match.

## 9. The caption

Built by `render.py` on the first render and written into `post.json`; a caption that no longer matches its fields fails the render with a `CAPTION:` line. Order:

1. `cover_answer` (so in the feed the cover asks and the caption answers)
2. `summary`
3. `Source: <outlet>, <source_domain>` with the photo credit on the next line when a photo ran
4. `Swipe for what to say at 5, at 10, and at 15.`
5. `The dinner table question: <table_question> Tell us what your kid said, and how old they are.`
6. hashtags

**Hashtag rule** (enforced by `render.py`, not auto-fixed). Exactly four tags, three of them fixed: `#Parenting`, `#KidsAndNews`, **one story tag**, `#DinnerTableNews`. The third slot is the only free one and it names what the story is actually about — a person, place, bill, company, event. It is never a category label (`#Economy`, `#Government`, `#GoodNews`, `#World`…) or a catch-all (`#News`, `#Politics`): the cover already prints the category, so repeating it spends the one free tag on nothing. `check_hashtags()` fails the render with a `HASHTAGS:` line on a wrong count, a wrong shape, or a generic story tag.

This rule exists because the guidance used to be "3–5 tags, last is `#DinnerTableNews`", which permitted both a fifth tag and a generic one. Under it, four of the first nine posts shipped a category label as a tag (`#economy` three times, `#goodnews` twice). Posts published before this rule are left as they went out.

## 10. Images from Wikimedia Commons

`commons.yml` is dispatched with `subject` (exact Wikipedia article title) and `slug`. `commons.py` reads the Wikipedia page image, requires at least 800px on the short side and a CC or public-domain license, downloads it, and commits `data/images/<slug>.jpg`, `.json` (subject, file, commons_file, size, license, artist, page, credit line), and `.log`. The run waits about 90 seconds, pulls, and uses the image if the JSON exists; otherwise it carries on without a photo.

## 11. Publishing to Instagram

`publish.yml` is dispatched with `action=publish` and `folder=posts/<slug>`. `publish.py` uses the Instagram API with Instagram Login (Graph API v23): it reads the numbered JPGs in the folder (five today, six in older posts), creates a carousel item per image from its `raw.githubusercontent.com` URL, creates the carousel container with the caption, polls until finished, publishes, and commits `posts/<slug>/published.json` with id, permalink, and timestamp. It refuses to publish a folder that already has `published.json`.

`refresh.yml` runs weekly and rotates the long-lived token, writing the new value into the `IG_ACCESS_TOKEN` repository secret with a PAT.

Secrets required: `IG_ACCESS_TOKEN` (Instagram long-lived token for the business/creator account), `GH_PAT` (repo-scoped, to update the secret).

## 12. Timing and the veto window

- `config.json` slots: morning 07:00, noon 12:00, evening 20:00 Central. `publish_window_minutes: 10`.
- The scheduled task fires 40 minutes before each window opens: 06:10, 11:10, 19:10 Central.
- At the start of the run, `python target.py <slot>` draws the publish minute uniformly within ± 10 minutes of the slot (11:50–12:10 for noon) using the system random source. Drawn once; recorded in the log as `publish_target`; reported in the notification as "Posts at 11:57 CT".
- Every slot builds two posts: the primary in `posts/<slug>/` and the alternate in `posts/<slug>-alt/`, from a different category. The primary publishes unless Dan replies "alt".
- After building and pushing, the run dispatches `publish.yml` with `publish_at` set to the target and ends its turn with a three-line summary (primary, alternate, "Posts at 11:57 CT") plus "Reply kill, skip, or hold to stop it, or alt to run the alternate instead." Ending the turn is what sends Dan's phone notification.
- The timer is the workflow's: the job sleeps until `publish_at`, pulls `main`, and stops if `<folder>/HOLD` exists. Otherwise it publishes and commits the permalink to `published.json` and to the slot's log entry. No Claude session needs to be awake at the target. (The session's own wake-up failed to fire twice on 2026-09-14 after Dan's replies; the post went out 52 minutes late that evening.)
- Dan's replies wake the session: kill / skip / hold pushes a HOLD file and cancels the run; alt holds the primary and dispatches the alternate for the same target; an edit or swap is pushed to `main` before the target, or the run is cancelled and re-dispatched. If the target has passed when the build finishes, it dispatches without `publish_at` and publishes at once.
- A session wake-up is still armed for the target plus three minutes, but only to send Dan the permalink.
- `dry_run: true` in config does everything except dispatch the publish.

## 13. Logs and failure handling

`data/log.json` is a list of entries: `slug, date, slot, category, headline, photo, cover_band, publish_target, publish_run, chosen, alternate, published, published_at, note`. `alternate` holds the second post's folder, category, headline and photo flag; `chosen` is `primary`, `alternate`, or `none`, and `publish.py` sets it when a post goes live. An alternate that did not run never counts as having run. The note records every judgment call: skipped clusters and why, source situation, rule firings, anything unusual. Rules that read the log: 7-day story repeat, lead-subject-per-day, photo-subject and photo-frequency, cover band rotation.

If a step fails after two tries the run writes `runs/<slug>.log` describing what happened, pushes it, and stops. Known failure it has handled: Instagram returning "API access blocked" (OAuthException 200) for a few hours; the run logged it and stopped, and the post published cleanly later.

## 14. Environment constraints (Claude Code cloud sandbox)

- News sites, Wikimedia, and Instagram are unreachable from the sandbox. Article text comes from `data/articles.json`; images and publishing go through Actions.
- `gh api` can read but returns 403 on workflow dispatch in scheduled runs. Dispatch with the GitHub MCP tool (`actions_run_trigger`, `run_workflow`).
- Chromium is preinstalled for Playwright; `pip install --break-system-packages feedparser requests pyyaml playwright pillow` covers the rest.
- `gh` installs with apt (the release tarball is blocked).
- A session holds one pending wake-up at a time, the user's next message replaces it, and a wake-up re-armed after a reply has failed to fire. Nothing that must happen on time is left to a session wake-up.

## 15. Rebuild checklist

1. Create the repo with the files in §4. Copy the fonts. Set `config.json`.
2. Add secrets `IG_ACCESS_TOKEN` and `GH_PAT`. Run `publish.yml` with `action=verify` to confirm the token.
3. Enable `fetch.yml`; confirm `data/headlines.json` and `data/articles.json` update hourly.
4. Dispatch `commons.yml` once with a known subject to confirm images commit to `data/images/`.
5. Render the reference post: `python render.py posts/samples-v2-2026-09-13-evening/post.json /tmp/out/` should exit 0 and produce five JPGs.
6. Create the scheduled Claude task with the repo selected and the prompt: "Clone https://github.com/dinnertablenews/dtn and follow TASK.md exactly. Do not ask questions." Schedule it at 06:10, 11:10, and 19:10 America/Chicago.
7. Set `dry_run: true` for the first scheduled run, check the output and the notification, then set it to `false`.

## 16. Measurement

Instagram insights per post: reach, saves, shares, comments. Record them in the log entry a day after publishing when comparing changes. The first five-slide post is `2026-09-14-test` (September 14, 2026); anything before it is the six-slide format with the headline-first caption, and is the baseline.

## 17. Decisions and their reasons

- **Cover leads with the kid's question, not the headline.** The headline is what every news account shows; the question is the account's promise. The full summary moved to the caption so the cover gives a reason to swipe.
- **Questions live on the age card.** A parent of one kid stays on one card and gets the script and the awkward question together.
- **No brand card.** The last slide is the comment prompt. The pitch is one follow line beneath it.
- **Date on the cover, no slot or time.** The posts are about the day's news and should say so; someone opening a post hours later should never see "tonight" or "noon".
- **Layout rule forces shorter text rather than smaller type.** The three age cards must look identical in weight.
- **Caption is generated.** Order matters for engagement and a rule alone drifts; a builder does not.
- **Random publish minute.** Same-minute posting three times a day looks automated. The window is ± 10 minutes, drawn from the system random source, and the run starts early enough to build two posts before it opens.
- **The timer is a GitHub Action, the veto is a file.** The session's wake-up lost two posts' timing in one day. A workflow job sleeping to `publish_at` needs nobody awake, and a HOLD file on `main` is a veto that works from any device with git access.
- **Two posts per slot.** Dan chooses between a primary and an alternate from a different category rather than approving or rejecting one story. The alternate costs a second build and buys a real choice in the window.
