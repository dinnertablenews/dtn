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

Two settings live at the top of `site.py`: `EMAIL_FORM_ACTION` (empty until a provider is
picked — until then the follow section shows the Instagram card rather than a form that
does nothing) and `INSTAGRAM`.

