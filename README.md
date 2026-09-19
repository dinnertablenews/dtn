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

Two settings live at the top of `site.py`: `EMAIL_FORM_ACTION` (empty until a provider is
picked — until then the follow section shows the Instagram card rather than a form that
does nothing) and `INSTAGRAM`.

