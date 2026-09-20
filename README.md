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
question), `/archive/` (every story as a card, searched and filtered in the browser), a
page per post at `/p/<slug>/`, `/about/`, an RSS feed and a sitemap.

The archive ships every card and pages them twelve at a time in the browser. Searching or
picking a category filters the cards already on the page and returns to the first twelve,
newest first; "Load more" adds another twelve. At a few hundred posts this stays smaller
and faster than a JSON round trip and works from disk — revisit it when the archive runs
to four figures and shipping every card stops being cheap.

The whole site turns on one control: pick your kid's age once and every story, question
and answer on the page follows. A second control, top right, switches light and dark; it
follows the system until someone overrides it, and the override wins from then on.

The front page runs its three stories abreast from 940px up, as cards: the whole card is
the link, so it gets an edge to be the extent of. The columns share a baseline — the
source line is pushed to the foot of each story so the three line up however long the
answers run, and the footer always stacks onto two lines so a long outlet name cannot
break that.

Where a card cannot be hovered the age's colour has no way to appear at all, so the whole
border carries it instead of the neutral hairline. The rule is keyed to
`@media (hover:none)` rather than a screen width, because that is the actual reason: a
tablet cannot hover either, and a desktop window dragged narrow still can. The border
rather than a tint, which washes a whole page of same-age cards, or a shadow, which is
invisible on the dark theme.

The about page carries the reasoning behind the three bands: Piaget's stages and what each
implies for how a story has to be told, Vygotsky on why the words go to the parent, Cantor
on why some stories carry a "don't raise it" flag, and Kuhn on why every story ends in a
question. It names frameworks and what follows from them. It cites no study, quotes no
statistic and claims no result, deliberately — a page arguing for its own rigour is the
worst place to put a citation a reader cannot check.

It is written in Dan's voice and checked against the Wikipedia:Signs of AI writing field
guide: no em dashes, no "not just X but also Y", no three-item lists used as filler, no
puffery verbs, no closing summary. It opens on a concrete scene rather than a thesis, which
is how Dan opens. Curly quotes stay — that guide lists them as a tell, but says so for a
project whose house style is straight quotes; here they are correct typography and they
match the slides, which `typo()` sets the same way.

The card click is a script, and the headline inside it is a real link, so the card still
works with JavaScript off, from a keyboard, and for a crawler. The script bows out of a
click on a real link, and out of a click that ends a text selection; ⌘ and middle click
open a tab, as they would on any link. The pointer cursor is added by that script rather
than by the stylesheet, so it never promises a click that nothing is listening for.

The slot — morning, noon, evening — is not printed anywhere. A reader gains nothing from
"Noon". `slot_name` stays on the post because the digest feed reads it to know a day has
run its evening and is safe to mail. `--page` is 1120px on the front page, the archive
and the about page, so the masthead is the same object everywhere and does not resize as
you move between them. A post keeps 720px.

Where a page is prose rather than a grid, the `text` body class holds the reading column
and the rules between sections to 62ch while the masthead stays wide. Centring that column
under a left-aligned wordmark was the alternative and it reads worse: two left edges, and
the mark stranded on its own.

The mark is `render.py`'s `wordmark()`: three lines with the dots beneath, the dot 45% of
the type size. The site and the slides carry one lockup. The choice is an attribute on `<html>` and a
`localStorage` key, so it survives navigation and costs nothing to switch. All three
versions are in the HTML, so the page works with JavaScript off.

The stylesheet ships under a name carrying a hash of its own contents
(`assets/site.<hash>.css`). It is the one file that changes on most deploys and the one
file a browser is told it may keep, and new markup served against an old stylesheet fails
quietly rather than loudly: the archive once filtered correctly, printed the right count,
and hid nothing, because the rule that hides a card was in a stylesheet the reader had not
been given yet. A changed stylesheet is now a different URL.

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

## First visit

`TOUR` in `site.py` holds a four-step walkthrough, shown once per browser on the front
page only and remembered under `dtn-tour`. Three steps point at something — the age pills,
the first story card, the Archive link — and the fourth is a centred modal that asks the
reader to share. The dim is the spotlight's own box-shadow, so a separate full-screen
layer sits underneath it: a shadow does not take a click, and without that layer a reader
could tap a story card straight through the tour.

It can be escaped, by Skip or by Escape, and either counts as seen. A walkthrough nobody
can leave is a walkthrough that traps the reader whose browser lays it out wrong.

`SHARE_TEXT` and `SHARE_SUBJECT` set what gets sent. Any `.share` button opens an SMS on a
touch device and a mail client everywhere else, keyed to the same `(hover:none) and
(pointer:coarse)` test the cards use. The `sms:?&body=` spelling is the form both iOS and
Android accept; it wants testing on real handsets.

The about page names all ten outlets, read out of `feeds.yaml` at build time by
`outlets()` rather than typed into the copy. The source list is the claim that page makes,
so it should not be possible for the two to disagree. NASA is excluded: it sits under
`background:` and supplies public-domain pictures, not stories.

## Categories

`CATEGORIES` is the list, in the order the archive shows it: World, U.S., Politics,
Business, Technology, Science, Health, Climate, Culture, Sports, Good news. The archive
prints all of them and disables the ones with nothing behind them, so the row is the set
the site commits to rather than whatever happens to have run.

`REMAP` maps the labels retired from the old list — Government to Politics, Economy to
Business, Security to World — as posts are loaded. Their covers still print the label they
shipped with; this governs only how the site files and filters them.

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

