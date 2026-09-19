# Dinner Table News — fetcher

Hourly GitHub Action that pulls the allowlisted feeds in `feeds.yaml` and writes
`data/headlines.json` (last 48 hours, deduped). Downstream, the scheduled Claude task
reads that file to pick the day's three stories and build the carousel.

Add or remove a source by editing `feeds.yaml`. Nothing outside that file is ever fetched.

# Dinner Table News — website

`site.py` builds a static site from the posts that actually went out and writes it to
`site/` (gitignored — it is a derived artifact, rebuilt on every deploy).

    python3 site.py            build
    python3 site.py --serve    build, then serve it on http://localhost:8000

A post reaches the web when it has a `published.json`, so drafts, unused alternates and
samples never appear. `2026-09-15-evening-alt` is on the site and `2026-09-15-evening` is
not, because the alternate is the one that ran.

What it writes: the front page (the latest three stories and tonight's dinner table
question), `/archive/` (every story, searched and filtered in the browser), a page per
post at `/p/<slug>/`, `/about/`, an RSS feed and a sitemap.

The whole site turns on one control: pick your kid's age once and every story, question
and answer on the page follows. The choice is an attribute on `<html>` and a
`localStorage` key, so it survives navigation and costs nothing to switch. All three
versions are in the HTML, so the page works with JavaScript off.

Links are written relative to the page that carries them, so one build works at
`github.io/dtn/`, at a custom domain, or opened from disk. Absolute URLs — the feed, the
sitemap, the `og:` tags — come from `DTN_BASE_URL`, which the workflow sets from whatever
Pages is actually serving.

Deployed by `.github/workflows/site.yml` on every push to `main` that touches a post or
the generator. Enable it once under **Settings → Pages → Source: GitHub Actions**.

## Domain

`dinnertablenews.com`, set in `site.py` as `DOMAIN`. That constant is what the feed, the
sitemap, the canonical links and the `og:` tags say, and `site.py` writes it to
`site/CNAME` on every build — deploying from Actions there is no branch for GitHub to keep
the custom domain in, so it has to travel in the artifact or a deploy can drop it.

DNS at the registrar, alongside the `_github-pages-challenge-dinnertablenews` TXT record
that verified the domain:

| Name | Type | Value |
|---|---|---|
| `@` | A | `185.199.108.153` |
| `@` | A | `185.199.109.153` |
| `@` | A | `185.199.110.153` |
| `@` | A | `185.199.111.153` |
| `@` | AAAA | `2606:50c0:8000::153` |
| `@` | AAAA | `2606:50c0:8001::153` |
| `@` | AAAA | `2606:50c0:8002::153` |
| `@` | AAAA | `2606:50c0:8003::153` |
| `www` | CNAME | `dinnertablenews.github.io` |

Every value in full, one per row: an abbreviated list is a typo waiting to happen, and a
registrar will accept `.109.153` without complaint.

Four A records, not one — they are GitHub's edge, and all four go in. Use **A records at
the apex, never an ALIAS or CNAME flattening**: the apex also has to carry Proton's MX
records, and some registrars will not serve MX next to a flattened apex CNAME.

The registrar is GoDaddy, which ships two records that have to go or the site breaks
intermittently rather than cleanly:

- an `A @` record labelled **WebsiteBuilder Site** — its parked-page IP. Left in place the
  apex answers with five addresses, GitHub's four and GoDaddy's one, and roughly a fifth
  of visitors land on a parking page. Edit it into the first GitHub address rather than
  adding a fifth record.
- a `www` CNAME pointing at the apex. Edit it to `dinnertablenews.github.io`; a second
  `www` CNAME is refused, because a name can only carry one.

Check too that no **domain forwarding** is set on the domain. It sits in front of DNS and
overrides correct records.

Then **Settings → Pages**: set the custom domain to `dinnertablenews.com`, wait for the
check to pass, and tick **Enforce HTTPS**.

## The morning email

Buttondown, sending from the feed rather than from a second pipeline.

There are two feeds, and they are not interchangeable:

| Feed | Shape | For |
|---|---|---|
| `/feed.xml` | one item per story, three a day | feed readers |
| `/feed-daily.xml` | one item per day, all three stories, all three ages | the email |

Point Buttondown's RSS-to-email at **`/feed-daily.xml`**. Pointed at `feed.xml` it would
send three emails a day, which is not what the site promises anyone.

A digest item appears only once a day has run its evening slot. A day still filling would
otherwise go out as a third of itself at 7am with no way to send the rest. So the email
that lands on Saturday morning carries Friday's three stories, complete.

The email body is built by `digest_html()`: inline styles only, no classes, no `oklch()`
— mail clients keep none of those, and one that cannot parse a colour renders it black
rather than approximating it. `MAIL_HUE` holds the three band colours as hex for that
reason; they are the site's light-mode values converted once.

Set `BUTTONDOWN` at the top of `site.py` to the account name and the signup form turns on.
While it is empty the follow section shows the Instagram card instead — a form that posts
nowhere is worse than an honest link. `DTN_BUTTONDOWN=<name> python3 site.py` previews the
form without committing a name.

### What signup asks

Everyone gets the same email — all three ages, one send. Signup still asks which ages a
subscriber cares about, as checkboxes posting Buttondown `tag` values (`ages-5-7`,
`ages-8-12`, `ages-13-17`).

That is not segmentation, it is the evidence that would justify segmenting later. A list
that never asked cannot be split without emailing everyone to ask, so the question is
cheaper now than at any later point.

The box for the age the reader has been reading at is checked on arrival, so somebody who
ignores the question still answers it. It is set on load only: touching the page's age
control afterwards must not rewrite what they said. Checkboxes rather than a single
choice, because a parent with a 6-year-old and a 14-year-old has two honest answers.

Two things to confirm against a real Buttondown account, both of which change one constant
if they are wrong: that the embed endpoint accepts repeated `tag` fields for a multiple
selection, and that tags are available on the plan in use. If they are not, set
`AGE_FIELD = "metadata__ages"` and the same answers arrive as subscriber metadata.

RSS-to-email is a paid add-on on top of Buttondown's free tier, which covers the first
hundred subscribers.

